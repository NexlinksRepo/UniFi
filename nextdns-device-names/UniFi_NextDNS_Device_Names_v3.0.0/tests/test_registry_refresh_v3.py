import copy
import contextlib
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v3


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=self.root/'native.conf'
        self.clean='port=20201\ncache-size=20000\n'
        self.config.write_bytes((self.clean+v3.block('127.0.0.1#5053')).encode())
        self.row={'path':str(self.config),'port':20201,'interfaces':['br0'],'listen_addresses':[],
                  'target':'127.0.0.1#5053','profiles':['abcdef'],'argv':['dnsmasq'],
                  'base_sha256':v3.hashlib.sha256(self.clean.encode()).hexdigest()}
        self.plan={'profiles':['abcdef'],'proxies':[],'forwarders':[self.row]}
        self.state={'active':True,'stage':'active','plan':copy.deepcopy(self.plan)}
        self.registry={'version':2,'enabled':True,'expires_unix':int(time.time())+60,
                       'profiles':{'abcdef':{'by_ip':{},'by_mac':{}}}}
        self.manager=v3.Manager()
        self.manager.state_file=self.root/'state.json'
        self.runtime=patch.object(v3,'RUNTIME',self.root)
        self.runtime.start();self.addCleanup(self.runtime.stop)
        v3.save(self.root/'devices.json',self.registry)
        v3.save(self.manager.state_file,self.state)

    def test_old_registry_stays_enabled_until_atomic_publication(self):
        before=(self.root/'devices.json').read_bytes()
        writes=[]; original_save=v3.save
        replacement=dict(self.registry,expires_unix=self.registry['expires_unix']+1)
        def record(path,data):
            if Path(path).name=='devices.json':writes.append(copy.deepcopy(data))
            return original_save(path,data)
        def collect(plan):
            self.assertEqual((self.root/'devices.json').read_bytes(),before)
            self.assertTrue(v3.load(self.root/'devices.json')['enabled'])
            v3.save(self.root/'devices.json',replacement)
            return 'test'
        with patch.object(v3,'save',side_effect=record),patch.object(self.manager,'collect',side_effect=collect),patch.object(self.manager,'check_listeners'),patch.object(self.manager,'restart') as restart:
            self.assertEqual(self.manager.reconcile(self.plan,self.state),0)
        self.assertEqual(writes,[replacement])
        restart.assert_not_called()
        self.assertTrue(v3.load(self.root/'devices.json')['enabled'])

    def test_failed_refresh_keeps_old_bytes_and_original_expiry(self):
        before=(self.root/'devices.json').read_bytes()
        with patch.object(self.manager,'collect',side_effect=v3.Failure('source unavailable')):
            with self.assertRaises(v3.RegistryRefreshError) as raised:
                self.manager.reconcile(self.plan,self.state)
        with patch.object(self.manager,'check_listeners'):
            self.assertTrue(self.manager.keep_registry_after_refresh_failure(self.plan,self.state,raised.exception))
        self.assertEqual((self.root/'devices.json').read_bytes(),before)
        self.assertEqual(v3.load(self.root/'devices.json')['expires_unix'],self.registry['expires_unix'])
        self.assertEqual(self.state['registry_refresh_failures'],1)

    def test_failed_atomic_rename_leaves_old_registry_intact(self):
        before=(self.root/'devices.json').read_bytes()
        def collect(plan):
            with patch.object(v3.legacy.os,'replace',side_effect=OSError('publication failed')):
                v3.save(self.root/'devices.json',dict(self.registry,expires_unix=self.registry['expires_unix']+1))
        with patch.object(self.manager,'collect',side_effect=collect),self.assertRaises(v3.RegistryRefreshError):
            self.manager.reconcile(self.plan,self.state)
        self.assertEqual((self.root/'devices.json').read_bytes(),before)
        self.assertFalse(list(self.root.glob('.ndn-*')))

    def test_expired_disabled_invalid_or_wrong_profile_not_kept(self):
        for change in [{'expires_unix':1},{'enabled':False},{'expires_unix':None},
                       {'expires_unix':int(time.time())+1000},{'profiles':{'123456':{}}}]:
            with self.subTest(change=change):
                v3.save(self.root/'devices.json',dict(self.registry,**change))
                self.assertFalse(self.manager.current_registry_usable(self.plan,self.state))
        (self.root/'devices.json').write_text('{broken')
        self.assertFalse(self.manager.current_registry_usable(self.plan,self.state))

    def test_new_profile_disables_old_registry_before_refresh(self):
        changed=copy.deepcopy(self.plan); changed['profiles']=['123456'];changed['forwarders'][0]['profiles']=['123456']
        def collect(plan):
            self.assertFalse(v3.load(self.root/'devices.json')['enabled'])
            raise v3.Failure('new source unavailable')
        with patch.object(self.manager,'collect',side_effect=collect),self.assertRaises(v3.RegistryRefreshError):
            self.manager.reconcile(changed,self.state)
        self.assertFalse(self.manager.current_registry_usable(changed,self.state))

    def test_changed_target_and_interface_are_attribution_boundaries(self):
        for key,value in [('target','127.0.0.1#5054'),('interfaces',['br2']),('port',20202)]:
            changed=copy.deepcopy(self.plan);changed['forwarders'][0][key]=value
            self.assertFalse(self.manager.same_active_scope(changed,self.state))

    def test_comment_cache_hash_change_does_not_disable_valid_names(self):
        changed=copy.deepcopy(self.plan);changed['forwarders'][0]['base_sha256']='changed-native-file'
        self.assertTrue(self.manager.same_active_scope(changed,self.state))

    def test_bad_listener_health_cannot_reuse_old_registry(self):
        with patch.object(self.manager,'check_listeners',side_effect=v3.Failure('listener missing')):
            self.assertFalse(self.manager.keep_registry_after_refresh_failure(self.plan,self.state,v3.RegistryRefreshError('refresh failed')))

    def test_non_refresh_failure_cannot_reuse_old_registry(self):
        self.assertFalse(self.manager.keep_registry_after_refresh_failure(self.plan,self.state,v3.Failure('unsupported topology')))

    def run_one_manager_tick(self,inspection):
        v3.save(self.root/'desired.json',{'enabled':True,'committed':True,'deadline':None})
        callbacks={}
        def register(sig,callback):callbacks[sig]=callback
        def sleep(_):callbacks[signal.SIGTERM]()
        if isinstance(inspection,Exception):kwargs={'side_effect':inspection}
        else:kwargs={'return_value':inspection}
        with patch.object(v3,'INSTALL',self.root),patch.object(self.manager,'lock',side_effect=lambda:contextlib.nullcontext()),patch.object(v3.signal,'signal',side_effect=register),patch.object(v3.time,'sleep',side_effect=sleep),patch.object(self.manager,'binary_check'),patch.object(self.manager,'inspect',**kwargs),patch.object(self.manager,'restore'):
            self.manager.manager()

    def test_manager_initial_observation_of_same_scope_has_no_off_gap(self):
        before=(self.root/'devices.json').read_bytes()
        self.run_one_manager_tick(self.plan)
        self.assertEqual((self.root/'devices.json').read_bytes(),before)

    def test_manager_invalid_discovery_disables_enrichment_immediately(self):
        self.run_one_manager_tick(v3.Failure('unsupported upstream'))
        self.assertFalse(v3.load(self.root/'devices.json')['enabled'])

    def test_manager_changed_profile_disables_before_settling(self):
        changed=copy.deepcopy(self.plan);changed['profiles']=['123456'];changed['forwarders'][0]['profiles']=['123456']
        self.run_one_manager_tick(changed)
        self.assertFalse(v3.load(self.root/'devices.json')['enabled'])

    def test_manager_cache_hash_change_does_not_switch_off_names(self):
        changed=copy.deepcopy(self.plan);changed['forwarders'][0]['base_sha256']='cache-change'
        before=(self.root/'devices.json').read_bytes()
        self.run_one_manager_tick(changed)
        self.assertEqual((self.root/'devices.json').read_bytes(),before)

    def test_explicit_restore_still_disables_names(self):
        with patch.object(self.manager,'mounted',return_value=False):
            self.manager.restore({'stage':'stock'},'Explicit disable')
        self.assertFalse(v3.load(self.root/'devices.json')['enabled'])


if __name__=='__main__':unittest.main()
