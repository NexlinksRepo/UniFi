import base64
import importlib.util
import json
import sys
import tempfile
import time
import unittest
import contextlib
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import v3 as v2

def stamp(profile='abcdef',host='dns.nextdns.io'):
    lp=lambda s:bytes([len(s)])+s.encode()
    return 'sdns://'+base64.urlsafe_b64encode(b'\x02'+b'\0'*8+lp('')+b'\0'+lp(host)+lp('/'+profile)).decode().rstrip('=')

def proxy(port=5053,profile='abcdef'):
    return f"listen_addresses=['127.0.0.1:{port}']\ncache=false\nserver_names=['n']\n[static.n]\nstamp='{stamp(profile)}'\n"

def layout():
    return {'p':proxy()}, {'main':'interface=br0\ninterface=br2\ncache-size=20000\nserver=127.0.0.1#5053\n',
                          'wan':'port=20201\ninterface=eth9\nconntrack\nconnmark-allowlist=1\n'}

class DiscoveryTests(unittest.TestCase):
    def test_all_forwarders_and_no_hardcoded_interface_or_port(self):
        p,f=layout(); f['wan']=f['wan'].replace('20201','23456').replace('eth9','eth42')
        plan=v2.discover(p,f)
        row=next(x for x in plan['forwarders'] if x['path']=='wan')
        self.assertEqual(row['interfaces'],['eth42'])
        self.assertEqual(row['target'],'127.0.0.1#5053')
        self.assertEqual(row['forwarding_path'],['127.0.0.1#23456','127.0.0.1#53','127.0.0.1#5053'])

    def test_multiple_proxy_profiles(self):
        p,f=layout(); p['p2']=proxy(5054,'123456')
        f['second']='port=20202\ninterface=eth8\nserver=127.0.0.1#5054\n'
        plan=v2.discover(p,f)
        self.assertEqual(plan['profiles'],['123456','abcdef'])
        self.assertEqual(next(x for x in plan['forwarders'] if x['path']=='second')['profiles'],['123456'])

    def test_external_conditional_mixed_and_unresolved_fail_closed(self):
        p,f=layout()
        for upstream in ['8.8.8.8','/corp.example/127.0.0.1#5053','127.0.0.1#65536','127.0.0.1#7777']:
            with self.subTest(upstream=upstream),self.assertRaises(v2.Failure):
                v2.discover(p,dict(f,wan='port=20201\nserver='+upstream+'\n'))
        with self.assertRaises(v2.Failure):
            v2.discover({'p':proxy().replace(stamp(),stamp(host='example.com'))},f)

    def test_cycle_and_duplicate_port(self):
        p,f=layout()
        with self.assertRaises(v2.Failure):
            v2.discover(p,dict(f,main='server=127.0.0.1#20201\n'))
        with self.assertRaises(v2.Failure):
            v2.discover(p,dict(f,wan='port=53\n'))

    def test_cache_and_policy_directives_preserved(self):
        p,f=layout(); original=f['wan']; patched=original+v2.block('127.0.0.1#5053')
        self.assertEqual(v2.strip_block(patched),original)
        self.assertEqual(v2.discover(p,f),v2.discover(p,dict(f,wan=patched)))
        self.assertIn('cache-size=20000',f['main'])

    def test_edited_managed_block_refused(self):
        with self.assertRaises(v2.Failure):
            v2.strip_block(v2.block('127.0.0.1#5053').replace('add-mac','extra-option'))

    def test_shared_upstream_and_includes_refused(self):
        p,f=layout()
        for content in ['server=8.8.8.8\n','conf-dir=/tmp/other\n','add-mac\n']:
            with self.assertRaises(v2.Failure):v2.discover(p,f,content)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.mac='00:11:22:33:44:55'
        self.lease={'mac':self.mac,'ip':'192.168.1.5','name':'DHCP'}

    def test_profile_ids_and_name_changes(self):
        a=v2.registry(['abcdef','123456'],[self.lease],[dict(self.lease,name='Alias')])
        first=a['profiles']['abcdef']['by_mac'][self.mac]
        second=a['profiles']['123456']['by_mac'][self.mac]
        self.assertNotEqual(first['id'],second['id'])
        b=v2.registry(['abcdef'],[dict(self.lease,ip='192.168.1.9')],[dict(self.lease,name='Renamed')])
        self.assertEqual(first['id'],b['profiles']['abcdef']['by_mac'][self.mac]['id'])
        self.assertEqual(len(first['id']),16)

    def test_unnamed_current_lease_blocks_stale_unifi_ip(self):
        other={'mac':'00:11:22:33:44:66','ip':self.lease['ip'],'name':'Old owner'}
        result=v2.registry(['abcdef'],[dict(self.lease,name=None)],[other])
        self.assertNotIn(self.lease['ip'],result['profiles']['abcdef']['by_ip'])

    def test_conflicting_mac_names_omitted(self):
        result=v2.registry(['abcdef'],[self.lease],[dict(self.lease,name='One'),dict(self.lease,name='Two')])
        self.assertNotIn(self.mac,result['profiles']['abcdef']['by_mac'])

    def test_ambiguous_ip_without_current_lease_is_not_labeled(self):
        other=dict(self.lease,mac='00:11:22:33:44:66',name='Other',current_ip=True)
        result=v2.registry(['abcdef'],[],[dict(self.lease,current_ip=True),other])
        self.assertNotIn(self.lease['ip'],result['profiles']['abcdef']['by_ip'])

    def test_historical_database_ip_is_not_a_current_owner(self):
        result=v2.registry(['abcdef'],[],[self.lease])
        self.assertNotIn(self.lease['ip'],result['profiles']['abcdef']['by_ip'])
        self.assertIn(self.mac,result['profiles']['abcdef']['by_mac'])

    def test_stale_neighbor_is_not_an_ip_only_identity(self):
        result=v2.registry(['abcdef'],[],[self.lease],[{'dst':self.lease['ip'],'lladdr':self.mac,'state':['STALE']}])
        self.assertNotIn(self.lease['ip'],result['profiles']['abcdef']['by_ip'])

    def test_unsafe_names_omitted(self):
        result=v2.registry(['abcdef'],[],[dict(self.lease,name='bad\r\nHeader: value')])
        self.assertFalse(result['profiles']['abcdef']['by_mac'])


class ReconciliationTests(unittest.TestCase):
    def test_restart_storm_is_refused_before_config_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); f=root/'native.conf'; f.write_text('port=20201\n')
            row={'path':str(f),'target':'127.0.0.1#5053','argv':['dnsmasq'],'base_sha256':v2.hashlib.sha256(f.read_text().encode()).hexdigest()}
            m=v2.Manager();m.state_file=root/'state.json'
            state={'reconciliations':[time.time()]*3}
            with patch.object(v2,'RUNTIME',root),self.assertRaises(v2.Failure):m.reconcile({'forwarders':[row],'proxies':[]},state)
            self.assertEqual(f.read_text(),'port=20201\n')

    def test_regeneration_reapplied_without_replacing_native_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); f=root/'native.conf'; f.write_text('port=20201\ncache-size=20000\n')
            row={'path':str(f),'target':'127.0.0.1#5053','argv':['dnsmasq'],'base_sha256':v2.hashlib.sha256(f.read_text().encode()).hexdigest()}
            plan={'forwarders':[row],'proxies':[],'profiles':['abcdef']}
            m=v2.Manager(); m.state_file=root/'state.json'; calls=[]
            with patch.object(v2,'RUNTIME',root),patch.object(v2,'run'),patch.object(m,'restart',side_effect=lambda x:calls.append(x)),patch.object(m,'collect',return_value='test'),patch.object(m,'check_listeners'):
                self.assertEqual(m.reconcile(plan,{}),1)
                self.assertEqual(v2.load(m.state_file)['failures'],0)
                self.assertIn('cache-size=20000',f.read_text())
                self.assertEqual(f.read_text().count(v2.BEGIN),1)
                self.assertEqual(m.reconcile(plan,{}),0)
                # Actual incident: native generator removes the managed block.
                f.write_text(v2.strip_block(f.read_text()))
                self.assertEqual(m.reconcile(plan,{}),1)
                self.assertEqual(len(calls),2)

    def test_configuration_race_does_not_overwrite_native_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); f=root/'native.conf'; f.write_text('port=20201\n')
            row={'path':str(f),'target':'127.0.0.1#5053','argv':['dnsmasq'],'base_sha256':'wrong'}
            m=v2.Manager(); m.state_file=root/'state.json'
            with patch.object(v2,'RUNTIME',root),self.assertRaises(v2.Failure):
                m.reconcile({'forwarders':[row],'proxies':[]}, {})
            self.assertEqual(f.read_text(),'port=20201\n')

    def test_recovery_restarts_clean_regenerated_forwarder_before_detach(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); f=root/'native.conf'; f.write_text('port=20201\n')
            m=v2.Manager(); m.state_file=root/'state.json'; calls=[]
            with patch.object(v2,'RUNTIME',root),patch.object(m,'restart',side_effect=lambda x:calls.append(x['path'])),patch.object(m,'mounted',return_value=False):
                m.restore({'managed':[{'path':str(f)}]},'test')
            self.assertEqual(calls,[str(f)])

    def test_failed_forwarder_recovery_keeps_stripping_proxy_mounted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); f=root/'native.conf'; f.write_text('port=20201\n')
            m=v2.Manager(); m.state_file=root/'state.json'
            with patch.object(v2,'RUNTIME',root),patch.object(m,'restart',side_effect=v2.Failure('failed')),patch.object(m,'mounted',return_value=True),patch.object(v2,'run') as command,self.assertRaises(v2.Failure):
                m.restore({'managed':[{'path':str(f)}]},'test')
            command.assert_not_called()
            self.assertEqual(v2.load(m.state_file)['stage'],'recovery_failed')

    def test_install_summary_never_claims_client_probe_proven(self):
        p,f=layout(); m=v2.Manager()
        from io import StringIO
        output=StringIO()
        with patch('sys.stdout',output):m.coverage(v2.discover(p,f),'ENABLED: configuration verified')
        self.assertIn('br0, br2',output.getvalue())
        self.assertIn('LAN attribution',output.getvalue()) if 'LAN attribution' in output.getvalue() else self.assertIn('Confirm names',output.getvalue())


class LifecycleTests(unittest.TestCase):
    def test_commit_enables_boot_only_after_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);v2.save(root/'desired.json',{'enabled':True,'committed':False,'deadline':time.time()+100})
            m=v2.Manager();m.state_file=root/'state.json';v2.save(m.state_file,{'active':True})
            with patch.object(v2,'INSTALL',root),patch.object(v2,'Manager',return_value=m),patch.object(m,'lock',return_value=contextlib.nullcontext()),patch.object(m,'binary_check'),patch.object(m,'inspect',return_value={}),patch.object(m,'reconcile') as verify,patch.object(v2,'run',return_value=v2.subprocess.CompletedProcess([],0)) as command,patch.object(sys,'argv',['v3.py','commit']):
                self.assertEqual(v2.main(),0)
            verify.assert_called_once()
            self.assertTrue(v2.load(root/'desired.json')['committed'])
            self.assertIsNone(v2.load(root/'desired.json')['deadline'])
            self.assertIn(['systemctl','enable',v2.SERVICE],[call.args[0] for call in command.call_args_list])

    def test_trial_expiring_during_validation_cannot_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);v2.save(root/'desired.json',{'enabled':True,'committed':False,'deadline':100})
            m=v2.Manager();m.state_file=root/'state.json';v2.save(m.state_file,{'active':True})
            with patch.object(v2,'INSTALL',root),patch.object(v2,'Manager',return_value=m),patch.object(m,'lock',return_value=contextlib.nullcontext()),patch.object(m,'binary_check'),patch.object(m,'inspect',return_value={}),patch.object(m,'reconcile'),patch.object(v2.time,'time',side_effect=[50,150]),patch.object(v2,'run') as command,patch.object(sys,'argv',['v3.py','commit']):
                self.assertEqual(v2.main(),1)
            command.assert_not_called()
            self.assertFalse(v2.load(root/'desired.json')['committed'])

    def test_linux_entrypoints_use_lf(self):
        for script in ROOT.glob('*.sh'):
            self.assertNotIn(b'\r',script.read_bytes(),script.name)

    def test_trial_defaults_to_five_minutes_and_does_not_enable_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); package=root/'package'; package.mkdir(); (package/'bin').mkdir()
            for name in ['v3.py','controller.py','manifest.json','bin/dnscrypt-proxy']:
                (package/name).write_text('{}' if name=='manifest.json' else 'fixture')
            m=v2.Manager(package); m.state_file=root/'run/state.json'
            plan={'forwarders':[],'proxies':[],'profiles':['abcdef']}
            calls=[]
            def command(args,**kwargs):
                calls.append(args)
                if 'start' in args:v2.save(m.state_file,{'active':True,'plan':plan})
                return v2.subprocess.CompletedProcess(args,0)
            before=int(time.time())
            with patch.object(v2,'RUNTIME',root/'run'),patch.object(v2,'INSTALL',root/'install'),patch.object(v2,'UNIT',root/'unit'),patch.object(v2,'Manager',return_value=m),patch.object(m,'lock',return_value=contextlib.nullcontext()),patch.object(m,'binary_check'),patch.object(m,'inspect',return_value=plan),patch.object(m,'coverage'),patch.object(m,'isolated_test'),patch.object(v2,'run',side_effect=command),patch.object(sys,'argv',['v3.py','trial']):
                self.assertEqual(v2.main(),0)
            desired=v2.load(root/'install/desired.json')
            self.assertFalse(desired['committed'])
            self.assertIn(desired['deadline']-before,[300,301])
            self.assertFalse(any('enable' in c for c in calls))

    def test_expired_trial_cannot_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); v2.save(root/'desired.json',{'enabled':True,'committed':False,'deadline':1})
            m=v2.Manager(); m.state_file=root/'state.json';v2.save(m.state_file,{'active':True})
            with patch.object(v2,'INSTALL',root),patch.object(v2,'Manager',return_value=m),patch.object(m,'lock',return_value=contextlib.nullcontext()),patch.object(v2,'run') as command,patch.object(sys,'argv',['v3.py','commit']):
                self.assertEqual(v2.main(),1)
            command.assert_not_called()

    def test_expiry_restores_without_committing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); v2.save(root/'desired.json',{'enabled':True,'committed':False,'deadline':1})
            m=v2.Manager();m.state_file=root/'state.json'
            with patch.object(v2,'INSTALL',root),patch.object(m,'lock',return_value=contextlib.nullcontext()),patch.object(m,'restore') as restore,patch.object(v2.signal,'signal'):
                m.manager()
            restore.assert_called_once()
            self.assertFalse(v2.load(root/'desired.json')['enabled'])


class APITests(unittest.TestCase):
    def test_paginated_official_adapter_and_no_key_in_results(self):
        with tempfile.TemporaryDirectory() as folder:
            key=Path(folder)/'key';key.write_text('fixture-secret')
            documents=[{'data':[{'id':'site-1'}],'totalCount':1},
                       {'data':[{'macAddress':'00:11:22:33:44:55','ipAddress':'192.168.1.5','name':'Office'}],'totalCount':2},
                       {'data':[{'macAddress':'00:11:22:33:44:66','ipAddress':'192.168.1.6','name':'TV'}],'totalCount':2}]
            seen=[]
            def fetch(path):seen.append(path);return documents.pop(0)
            with patch.object(Path,'stat',return_value=type('Stat',(),{'st_mode':0o100600})()):
                rows=v2.api_clients({'api_url':'https://console.example/proxy/network/integration','api_key_file':str(key)},fetch)
            self.assertEqual(len(rows),2)
            self.assertIn('offset=1',seen[-1])
            self.assertNotIn('fixture-secret',json.dumps(rows))

    def test_unusable_schema_is_not_silently_mapped(self):
        with tempfile.TemporaryDirectory() as folder:
            key=Path(folder)/'key';key.write_text('fixture')
            cfg={'api_url':'https://console.example/integration','api_key_file':str(key)}
            with patch.object(Path,'stat',return_value=type('Stat',(),{'st_mode':0o100600})()),self.assertRaises(v2.Failure):
                v2.api_clients(cfg,lambda p:{'unexpected':[]})

    def test_plaintext_api_url_refused(self):
        with self.assertRaises(v2.Failure):
            v2.api_clients({'api_url':'http://console.example','api_key_file':'unused'})


if __name__=='__main__':unittest.main()
