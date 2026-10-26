#!/usr/bin/env python3
"""External NextDNS v2 integration. This is not a native UniFi feature."""
import argparse
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request

import controller as legacy

Failure = legacy.Failure
atomic_write = legacy.atomic_write
SERVICE = 'nextdns-device-names-v2.service'
BEGIN = '# nextdns-device-names v2 begin'
END = '# nextdns-device-names v2 end'
INSTALL = Path('/data/nextdns-device-names-v2')
RUNTIME = Path('/run/nextdns-device-names-v2')
NATIVE = Path('/usr/sbin/dnscrypt-proxy')
UNIT = Path('/etc/systemd/system') / SERVICE


def run(args, timeout=15, check=True):
    p = subprocess.run([str(x) for x in args], text=True, capture_output=True, timeout=timeout)
    if check and p.returncode:
        raise Failure(f'{Path(str(args[0])).name} failed (exit {p.returncode})')
    return p


def load(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else ({} if default is None else default)


def save(path, value):
    atomic_write(path, json.dumps(value, indent=2) + '\n')


def strip_block(text):
    if BEGIN not in text and END not in text:
        return text
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise Failure('Incomplete/duplicate v2 block; manual review required')
    before, rest = text.split(BEGIN, 1)
    middle, after = rest.split(END, 1)
    if before and not before.endswith('\n'):
        raise Failure('Invalid managed block boundary')
    lines = middle.strip().splitlines()
    required = ['no-resolv', 'strip-subnet', 'strip-mac', 'add-subnet=32,128', 'add-mac']
    if lines[:5] != required or len(lines) != 6 or not re.fullmatch(r'server=127\.0\.0\.1#\d+', lines[5]):
        raise Failure('Edited managed block; refusing to remove unrelated settings')
    return before + after.removeprefix('\n')


def directives(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, _, value = line.partition('=')
        result.setdefault(key, []).append(value)
    return result


def endpoint(value):
    match = re.fullmatch(r'(127\.0\.0\.1)(?:#(\d+))?', value)
    if not match or not 1 <= int(match[2] or 53) <= 65535:
        raise Failure('Unsupported upstream: conditional, external, or non-IPv4-loopback path')
    return f'127.0.0.1#{int(match[2] or 53)}'


def discover(proxy_texts, forwarder_texts, included_text='', resolv='nameserver 127.0.0.1\n'):
    """Discover all inputs; refuse ambiguity instead of silently skipping a path."""
    proxies, targets, forwarders = [], {}, []
    for path, text in sorted(proxy_texts.items()):
        cfg = tomllib.loads(text)
        names = cfg.get('server_names', [])
        if not names or cfg.get('user_name') or cfg.get('forwarding_rules') or cfg.get('cloaking_rules') or cfg.get('query_meta') or cfg.get('edns_client_subnet'):
            raise Failure('Unsupported proxy selection, privilege drop, or forwarding configuration')
        profiles = set()
        for name in names:
            try:
                profiles.add(legacy.decode_stamp(cfg['static'][name]['stamp'])[1])
            except (KeyError, legacy.Failure) as exc:
                raise Failure('Every selected resolver must be a static NextDNS DoH resolver') from exc
        listeners = []
        for address in cfg.get('listen_addresses', []):
            match = re.fullmatch(r'127\.0\.0\.1:(\d+)', address)
            if not match or not 1 <= int(match[1]) <= 65535:
                raise Failure('Only local IPv4 loopback proxy listeners are currently supported')
            target = f'127.0.0.1#{int(match[1])}'
            if target in targets:
                raise Failure('Duplicate encrypted-proxy listener')
            targets[target] = {'config':path, 'profiles':sorted(profiles)}
            listeners.append(target)
        if not listeners:
            raise Failure('Proxy has no supported listeners')
        proxies.append({'path':path, 'profiles':sorted(profiles), 'listeners':listeners})
    shared = directives(included_text)
    if any(k in shared for k in ['server','resolv-file','conf-file','conf-dir','add-mac','add-subnet','strip-mac','strip-subnet']):
        raise Failure('A shared DHCP include changes DNS upstream/metadata; separate review required')
    default_servers = re.findall(r'^nameserver\s+(\S+)', resolv, re.M)
    if default_servers != ['127.0.0.1']:
        raise Failure('System resolver must use the inspected local forwarder')
    listeners = {}
    for path, raw in sorted(forwarder_texts.items()):
        text = strip_block(raw)
        d = directives(text)
        if any(k in d for k in ['conf-file','conf-dir','resolv-file','add-mac','add-subnet','strip-mac','strip-subnet']):
            raise Failure('Forwarder contains an unreviewed include or existing metadata')
        ports = d.get('port',['53'])
        if len(ports) != 1 or not ports[0].isdigit() or not 1 <= int(ports[0]) <= 65535:
            raise Failure('Forwarder has an unsupported port')
        port = int(ports[0])
        key = f'127.0.0.1#{port}'
        if key in listeners or key in targets:
            raise Failure('Duplicate DNS listener; cannot select a forwarding path')
        servers = d.get('server', [])
        if not servers and 'no-resolv' in d:
            raise Failure('Forwarder has no upstream')
        if len(servers) > 1:
            raise Failure('Multiple forwarder upstreams require explicit policy support')
        row = {'path':path, 'port':port, 'interfaces':d.get('interface',[]),
               'listen_addresses':d.get('listen-address',[]),
               'upstream':endpoint(servers[0]) if servers else '127.0.0.1#53',
               'base_sha256':hashlib.sha256(text.encode()).hexdigest()}
        forwarders.append(row)
        listeners[key] = row
    if not proxies or not forwarders:
        raise Failure('No complete NextDNS resolver topology found')
    for row in forwarders:
        seen, target = set(), row['upstream']
        path = [f'127.0.0.1#{row["port"]}']
        while target not in targets:
            if target in seen or target not in listeners:
                raise Failure('Forwarding cycle or unresolved upstream')
            seen.add(target)
            path.append(target)
            target = listeners[target]['upstream']
        row.update(target=target, profiles=targets[target]['profiles'], forwarding_path=path+[target])
    return {'proxies':proxies, 'forwarders':forwarders,
            'profiles':sorted({p for x in proxies for p in x['profiles']})}


def block(target):
    return BEGIN+'\nno-resolv\nstrip-subnet\nstrip-mac\nadd-subnet=32,128\nadd-mac\nserver='+target+'\n'+END+'\n'


def registry(profiles, leases, clients, neighbors=(), gateway_ips=(), gateway_name='UniFi (Gateway)'):
    # Current DHCP ownership blocks historical UniFi/neighbor attribution even
    # when the current owner has no usable name. Conflicting source rows are omitted.
    owners = {x['ip']:x['mac'] for x in leases}
    normalized = []
    conflicts = set()
    by_identity = {}
    ip_owners = {}
    for x in leases:
        ip_owners.setdefault(x['ip'],set()).add(x['mac'])
    for x in clients:
        mac = legacy.normalized_mac(x.get('mac'))
        name = x.get('name')
        if not mac or not legacy.good_name(name):
            continue
        if mac in by_identity and by_identity[mac] != name:
            conflicts.add(mac)
        by_identity[mac] = name
        # last_ip from the private database is historical, not current ownership.
        ip = legacy.client_ip(x.get('ip')) if x.get('current_ip') else None
        if ip and owners.get(ip,mac) != mac:
            ip = None
        if ip:
            ip_owners.setdefault(ip,set()).add(mac)
        normalized.append({'mac':mac,'ip':ip,'name':name})
    leases = [dict(x, name=None) if x['mac'] in conflicts else x for x in leases]
    normalized = [x for x in normalized if x['mac'] not in conflicts]
    rows = {}
    ambiguous_ips = {ip for ip,macs in ip_owners.items() if len(macs)>1}
    current_neighbors=[]
    for neighbor in neighbors:
        states=neighbor.get('state',[])
        states=[states] if isinstance(states,str) else states
        if set(states).intersection({'REACHABLE','DELAY','PROBE','PERMANENT'}):
            current_neighbors.append(neighbor)
    for profile in profiles:
        data = legacy.make_registry(profile, leases, normalized, neighbors=current_neighbors,
                                    gateway_ips=gateway_ips, gateway_name=gateway_name)
        data['by_ip'] = {ip:x for ip,x in data['by_ip'].items()
                         if ip not in ambiguous_ips and (ip not in owners or x.get('mac') == owners[ip])}
        for x in list(data['by_ip'].values()) + list(data['by_mac'].values()):
            stable = x.get('mac') or 'gateway'
            x['id'] = base64.b32encode(hashlib.sha256((profile+':'+stable).encode()).digest()).decode()[:16]
        rows[profile] = data
    return {'version':2,'enabled':True,'expires_unix':int(time.time())+90,'profiles':rows}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Failure('API redirects refused')


def api_clients(config, fetch=None):
    base = config['api_url'].rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Failure('API URL must be a credential-free HTTPS integration base URL')
    key_path = Path(config['api_key_file'])
    if key_path.stat().st_mode & 0o077:
        raise Failure('API key file must be readable only by its owner (chmod 600)')
    key = key_path.read_text().strip()
    if not key or '\n' in key or '\r' in key:
        raise Failure('Invalid API key file')
    ctx = ssl.create_default_context(cafile=config.get('api_ca_file'))
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), NoRedirect())
    def request(path):
        req = urllib.request.Request(base+path, headers={'X-API-Key':key,'Accept':'application/json'})
        with opener.open(req,timeout=5) as response:
            data = response.read(8*1024*1024+1)
            if len(data) > 8*1024*1024:
                raise Failure('API response too large')
            return json.loads(data)
    fetch = fetch or request
    def pages(path):
        offset = 0
        while True:
            doc = fetch(path+f'?offset={offset}&limit=100')
            if not isinstance(doc,dict) or not isinstance(doc.get('data'),list):
                raise Failure('Unsupported API response schema')
            data = doc['data']
            yield from data
            total = doc.get('totalCount')
            if not isinstance(total,int) or total < 0:
                raise Failure('API response missing totalCount')
            offset += len(data)
            if offset >= total:
                return
            if not data or offset > 100000:
                raise Failure('API pagination did not progress')
    rows = []
    for site in pages('/v1/sites'):
        site_id = str(site.get('id',''))
        if not re.fullmatch(r'[A-Za-z0-9-]+',site_id):
            raise Failure('Invalid API site identifier')
        for x in pages('/v1/sites/'+site_id+'/clients'):
            rows.append({'mac':x.get('macAddress'),'ip':x.get('ipAddress'),'name':x.get('name'),'current_ip':True})
    if rows and not any(legacy.normalized_mac(x['mac']) for x in rows):
        raise Failure('API does not expose usable client MACs; do not guess client identity')
    return rows


class Manager:
    def __init__(self, package=None):
        self.package = Path(package or Path(__file__).resolve().parent)
        self.manifest = load(self.package/'manifest.json')
        self.state_file = RUNTIME/'state.json'

    @contextlib.contextmanager
    def lock(self):
        import fcntl
        RUNTIME.mkdir(parents=True,mode=0o700,exist_ok=True)
        with (RUNTIME/'lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            yield

    def processes(self):
        result = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                argv = [x.decode() for x in (p/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
                if argv and argv[0] == str(NATIVE) and len(argv)==3 and argv[1]=='-config':
                    result.append({'kind':'proxy','path':argv[2],'argv':argv,'pid':int(p.name)})
                if argv and Path(argv[0]).name=='dnsmasq':
                    conf = [x.split('=',1)[1] for x in argv if x.startswith('--conf-file=')]
                    pidfile = [x.split('=',1)[1] for x in argv if x.startswith('--pid-file=')]
                    if len(conf)==1 and len(pidfile)==1 and int(Path(pidfile[0]).read_text())==int(p.name):
                        result.append({'kind':'forwarder','path':conf[0],'argv':argv,'pid':int(p.name)})
            except (OSError,ValueError,UnicodeError):
                pass
        return result

    def inspect(self):
        proc = self.processes()
        proxies = {str(p):p.read_text() for p in Path('/run').glob('dnscrypt-proxy*.toml')}
        forwarders = {str(p):p.read_text() for p in Path('/run/dnsmasq.dns.conf.d').glob('*.conf')}
        shared = ''.join(p.read_text()+'\n' for p in Path('/run/dnsmasq.dhcp.conf.d').glob('*') if p.is_file())
        plan = discover(proxies,forwarders,shared,Path('/etc/resolv.conf').read_text())
        for kind, rows in [('proxy',plan['proxies']),('forwarder',plan['forwarders'])]:
            for row in rows:
                matching = [x for x in proc if x['kind']==kind and x['path']==row['path']]
                if len(matching)!=1:
                    raise Failure('Missing/duplicate native process for '+row['path'])
                parent = re.search(r'^PPid:\s+(\d+)',(Path('/proc')/str(matching[0]['pid'])/'status').read_text(),re.M)[1]
                if not (Path('/proc')/parent/'comm').read_text().strip().startswith('ubios-udapi-ser'):
                    raise Failure('Unexpected DNS process supervisor')
                row['argv'] = matching[0]['argv']
        if len(proc) != len(plan['proxies'])+len(plan['forwarders']):
            raise Failure('An additional native resolver was detected without matching configuration')
        return plan

    def mounted(self):
        return any(x.split()[4]==str(NATIVE) for x in Path('/proc/self/mountinfo').read_text().splitlines())

    def binary_check(self):
        if sys.platform!='linux' or os.geteuid()!=0 or platform.machine()!='aarch64':
            raise Failure('Requires root on the inspected Linux ARM64 gateway')
        expected = self.manifest['candidate_sha256'] if self.mounted() else self.manifest['native_sha256']
        if legacy.digest(NATIVE)!=expected or legacy.digest(self.package/'bin/dnscrypt-proxy')!=self.manifest['candidate_sha256']:
            raise Failure('Native/candidate build differs from pinned compatibility hashes')

    def collect(self, plan, directory=RUNTIME):
        cfg = load(INSTALL/'settings.json',{'name_source':'postgres'})
        leases = legacy.lease_records(Path('/run/dnsmasq.lease').read_text())
        if cfg.get('name_source','postgres')=='api':
            rows = api_clients(cfg)
            source = 'official-api'
        elif cfg.get('name_source','postgres')=='postgres':
            rows = json.loads(run(['runuser','-u','postgres','--','psql','-X','-q','-At','-p','5434',
                                   '-d','unifi-network','-v','ON_ERROR_STOP=1','-c',legacy.UNIFI_SQL],timeout=5).stdout)
            if not isinstance(rows,list):
                raise Failure('Unsupported PostgreSQL client schema')
            source = 'private-postgres-schema'
        else:
            raise Failure('Unknown name source')
        neighbors = json.loads(run(['ip','-j','neigh','show']).stdout)
        addresses = json.loads(run(['ip','-j','addr','show']).stdout)
        gateway_ips = ['127.0.0.1','::1']+[a['local'] for x in addresses for a in x.get('addr_info',[]) if a.get('scope')=='global']
        data = registry(plan['profiles'],leases,rows,neighbors,gateway_ips,socket.gethostname()+' (Gateway)')
        save(Path(directory)/'devices.json',data)
        return source

    def restart(self,row):
        current = [x for x in self.processes() if x['path']==row['path']]
        if len(current)!=1:
            raise Failure('Cannot restart missing/duplicate process: '+row['path'])
        pid = current[0]['pid']
        os.kill(pid,signal.SIGTERM)
        until = time.monotonic()+12
        while time.monotonic()<until:
            fresh = [x for x in self.processes() if x['path']==row['path'] and x['pid']!=pid]
            if len(fresh)==1:
                return
            time.sleep(.2)
        raise Failure('Native supervisor did not respawn '+row['path'])

    def check_listeners(self,plan):
        addresses=json.loads(run(['ip','-j','-4','addr','show']).stdout)
        for row in plan['proxies']:
            for listener in row['listeners']:
                legacy.check_tcp_listener('127.0.0.1',int(listener.split('#')[1]))
        for row in plan['forwarders']:
            hosts={a['local'] for entry in addresses if entry['ifname'] in row.get('interfaces',[])
                   for a in entry.get('addr_info',[]) if a.get('scope')=='global'}
            for ip in row.get('listen_addresses',[]):
                try:
                    address=ipaddress.ip_address(ip)
                    if address.version==4 and not address.is_unspecified:hosts.add(str(address))
                except ValueError:raise Failure('Invalid explicit forwarder listen address')
            if not hosts:
                raise Failure('Cannot verify an IPv4 frontend listener for '+row['path'])
            for host in sorted(hosts):legacy.check_tcp_listener(host,row['port'])

    def coverage(self,plan,status):
        print('\nDetected DNS paths:',flush=True)
        for x in plan['forwarders']:
            interfaces = ', '.join(x['interfaces']) or 'native bound sockets (no interface directive)'
            print(f"  {Path(x['path']).stem}: interfaces {interfaces} | port {x['port']} | {' -> '.join(x['forwarding_path'])} | NextDNS profiles {', '.join(x['profiles'])} | {status}",flush=True)
        print('Coverage means configured forwarding and listener checks. Confirm names from each LAN/VLAN with probe-client.py.',flush=True)

    def inventory(self):
        print('\nResolver inventory (configuration detected; enrichment not yet verified):',flush=True)
        for p in sorted(Path('/run/dnsmasq.dns.conf.d').glob('*.conf')):
            d=directives(p.read_text())
            print(f"  {p.stem}: interfaces {', '.join(d.get('interface',[])) or 'native socket bindings'}; port {','.join(d.get('port',['53']))}",flush=True)
        for p in sorted(Path('/run').glob('dnscrypt-proxy*.toml')):
            cfg=tomllib.loads(p.read_text())
            print(f"  {p.name}: encrypted-proxy listeners {', '.join(cfg.get('listen_addresses',[]))}",flush=True)

    def reconcile(self,plan,state):
        save(RUNTIME/'devices.json',{'version':2,'enabled':False})
        # Save intent for every old/new path before mutation, including new instances.
        previous = {x['path']:x for x in state.get('managed',[])}
        previous.update({x['path']:x for x in plan['forwarders']})
        state['managed'] = list(previous.values())
        state['proxies'] = plan['proxies']
        save(self.state_file,state)
        # Abort on edits made after discovery. Never replace an entire native file.
        changes = []
        for row in plan['forwarders']:
            p = Path(row['path'])
            raw = p.read_text()
            clean = strip_block(raw)
            if hashlib.sha256(clean.encode()).hexdigest()!=row['base_sha256']:
                raise Failure('Native configuration changed during reconciliation')
            if not clean.endswith('\n'):
                raise Failure('Native configuration lacks a final newline')
            wanted = clean+block(row['target'])
            if wanted!=raw:
                changes.append((row,raw,wanted))
        if changes:
            recent=[t for t in state.get('reconciliations',[]) if time.time()-t<300]
            if len(recent)>=3:
                raise Failure('Repeated native regeneration; refusing a DNS restart loop')
            state['reconciliations']=recent+[time.time()]
            save(self.state_file,state)
        for row,raw,wanted in changes:
            p = Path(row['path'])
            if p.read_text()!=raw:
                raise Failure('Native configuration changed before write')
            atomic_write(p,wanted,0o644)
            run(row['argv']+['--test'])
        for row,_,_ in changes:
            self.restart(row)
        source = self.collect(plan)
        self.check_listeners(plan)
        state.update(active=True,stage='active',plan=plan,name_source=source,last_check_unix=int(time.time()),last_error=None,failures=0)
        save(self.state_file,state)
        return len(changes)

    def restore(self,state,reason):
        save(RUNTIME/'devices.json',{'version':2,'enabled':False})
        if state.get('stage')=='stock' and not self.mounted():
            return
        errors=[]
        for row in state.get('managed',[]):
            try:
                p=Path(row['path'])
                if p.exists():
                    raw=p.read_text(); clean=strip_block(raw)
                    if raw!=clean:
                        atomic_write(p,clean,0o644)
                        run(row['argv']+['--test'])
                    # A regenerated file can be clean while an old dnsmasq still
                    # runs with metadata options. Restart before detaching proxy.
                    self.restart(row)
                elif any(x['path']==row['path'] for x in self.processes()):
                    raise Failure('Live forwarder has lost its configuration: '+row['path'])
            except Exception as exc:
                errors.append(str(exc))
        if self.mounted() and not errors:
            try:
                if legacy.digest(NATIVE)!=self.manifest['candidate_sha256']:
                    raise Failure('Unexpected proxy mount; refusing to detach')
                result=run(['umount',NATIVE],check=False)
                if result.returncode:
                    if 'busy' not in result.stderr.lower():
                        raise Failure('Could not detach proxy mount')
                    run(['umount','--lazy',NATIVE])
                for row in state.get('proxies',[]):
                    self.restart(row)
                if legacy.digest(NATIVE)!=self.manifest['native_sha256']:
                    raise Failure('Stock binary hash mismatch after detach')
            except Exception as exc:
                errors.append(str(exc))
        state.update(active=False,stage='recovery_failed' if errors else 'stock',reason=reason,errors=errors)
        save(self.state_file,state)
        if errors:
            raise Failure('Recovery needs attention: '+'; '.join(errors))

    def isolated_test(self,plan):
        """Explicit tests only; never called by scheduled checks."""
        RUNTIME.mkdir(parents=True,mode=0o700,exist_ok=True)
        for proxy in plan['proxies']:
            with tempfile.TemporaryDirectory(prefix='test-',dir=RUNTIME) as folder:
                d=Path(folder)
                self.collect(plan,d)
                text=Path(proxy['path']).read_text()
                text,count=re.subn(r'(?m)^listen_addresses\s*=.*$',"listen_addresses=['127.0.0.1:15953']",text)
                if count!=1:
                    raise Failure('Cannot isolate proxy listener')
                text=re.sub(r'(?m)^(\s*(?:log_file|file)\s*=\s*)[\'\"].*[\'\"]\s*$',lambda m:m[1]+repr(str(d/'proxy.log')),text)
                atomic_write(d/'proxy.toml',text)
                run([self.package/'bin/dnscrypt-proxy','-config',d/'proxy.toml','-check'])
                with (d/'startup.log').open('wb') as output:
                    child=subprocess.Popen([str(self.package/'bin/dnscrypt-proxy'),'-config',str(d/'proxy.toml'),'-netprobe-timeout','5'],
                        env=dict(os.environ,NEXTDNS_DEVICE_NAMES_FILE=str(d/'devices.json')),stdout=output,stderr=output)
                    try:
                        deadline=time.monotonic()+18
                        while True:
                            try:
                                legacy.dns_exchange('127.0.0.1',15953,'example.com')
                                break
                            except (OSError,Failure):
                                if child.poll() is not None or time.monotonic()>deadline:
                                    raise Failure('Isolated proxy did not become ready')
                                time.sleep(.25)
                        legacy.dns_exchange('127.0.0.1',15953,'example.com',tcp=True)
                        data=load(d/'devices.json')
                        profile=proxy['profiles'][0]
                        chosen=[]; ids=set()
                        for ip,item in data['profiles'][profile]['by_ip'].items():
                            if item['id'] not in ids:
                                chosen.append((ip,item)); ids.add(item['id'])
                            if len(chosen)==2: break
                        if len(chosen)<2:
                            raise Failure('Two distinct named clients required for header diagnostic')
                        for ip,item in chosen:
                            name='ndn-check-'+os.urandom(8).hex()+'.example.com'
                            legacy.dns_exchange('127.0.0.1',15953,name,ip,item.get('mac') or None)
                            proof=load(d/'proof.json')
                            selected=proof.get('profile')
                            expected=data['profiles'].get(selected,{}).get('by_ip',{}).get(ip,{})
                            if selected not in proxy['profiles'] or proof.get('query_sha256')!=hashlib.sha256(name.encode()).hexdigest() or proof.get('device_id')!=expected.get('id') or proof.get('device_name')!=expected.get('name'):
                                raise Failure('Header proof mismatch')
                    finally:
                        child.terminate()
                        try: child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait(timeout=3)

    def manager(self):
        stopping=False
        def stop(*_):
            nonlocal stopping
            stopping=True
        signal.signal(signal.SIGTERM,stop)
        pending=None; settled=0; failures=0
        startup_until=time.monotonic()+120
        while not stopping:
            with self.lock():
                desired=load(INSTALL/'desired.json')
                state=load(self.state_file)
                if not desired.get('enabled'):
                    self.restore(state,'Disabled')
                    return
                if not desired.get('committed') and time.time()>=desired.get('deadline',0):
                    save(INSTALL/'desired.json',{'enabled':False,'committed':False})
                    self.restore(state,'Five-minute trial expired')
                    return
                try:
                    self.binary_check()
                    plan=self.inspect()
                    signature=json.dumps(plan,sort_keys=True)
                    if signature!=pending:
                        pending=signature; settled=0
                        # Names fail closed while the new native topology settles.
                        save(RUNTIME/'devices.json',{'version':2,'enabled':False})
                    settled+=1
                    if settled>=2:
                        if not self.mounted():
                            state.update(managed=plan['forwarders'],proxies=plan['proxies'],stage='mounting')
                            save(self.state_file,state)
                            run(['mount','--bind',self.package/'bin/dnscrypt-proxy',NATIVE])
                            for proxy in plan['proxies']: self.restart(proxy)
                        changes=self.reconcile(plan,state)
                        failures=0
                        if changes: print('Reconciled native configuration regeneration',flush=True)
                except Exception as exc:
                    if not state.get('managed') and time.monotonic()<startup_until:
                        state.update(active=False,stage='waiting_for_native_dns',last_error=str(exc))
                        save(self.state_file,state)
                        time.sleep(5)
                        continue
                    failures+=1
                    state.update(last_error=str(exc),failures=failures)
                    save(self.state_file,state)
                    if failures>=2:
                        self.restore(state,'Unsupported topology or failed recovery: '+str(exc))
                        # Do not loop indefinitely or auto-enable after an unsupported change.
                        save(INSTALL/'desired.json',{'enabled':False,'committed':False})
                        run(['systemctl','disable',SERVICE],check=False)
                        return
            for _ in range(5):
                if stopping: break
                time.sleep(1)
        with self.lock(): self.restore(load(self.state_file),'Manager stopped')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['discover','test','trial','commit','status','disable','rollback','manager','recover'])
    args=parser.parse_args()
    m=Manager()
    try:
        if args.command=='manager': m.manager(); return 0
        if args.command=='status':
            print(json.dumps({'desired':load(INSTALL/'desired.json'),'state':load(m.state_file),'native_integration':False},indent=2)); return 0
        if args.command in ['disable','rollback']:
            save(INSTALL/'desired.json',{'enabled':False,'committed':False})
            if UNIT.exists():
                run(['systemctl','disable','--now',SERVICE],timeout=310)
                if run(['systemctl','is-active','--quiet',SERVICE],check=False).returncode==0:
                    raise Failure('Manager did not stop; do not detach its live runtime')
            with m.lock(): m.restore(load(m.state_file),'Explicit disable')
            print('Enrichment disabled; stock DNS restored'); return 0
        if args.command=='recover':
            with m.lock(): m.restore(load(m.state_file),'Manager exited')
            return 0
        if args.command=='commit':
            with m.lock():
                desired=load(INSTALL/'desired.json'); state=load(m.state_file)
                if desired.get('committed'):
                    raise Failure('Already committed')
                if not desired.get('enabled') or time.time()>=desired.get('deadline',0) or not state.get('active'):
                    raise Failure('No ready, unexpired trial; nothing committed')
                m.binary_check(); plan=m.inspect(); m.reconcile(plan,state)
                if time.time()>=desired.get('deadline',0):
                    raise Failure('Trial expired during commit verification; nothing committed')
                run(['systemctl','is-active','--quiet',SERVICE])
                run(['systemctl','enable',SERVICE])
                desired.update(committed=True,deadline=None); save(INSTALL/'desired.json',desired)
                print('Committed. External boot service enabled; this is not native UniFi support.')
            return 0
        with m.lock():
            m.binary_check(); m.inventory(); plan=m.inspect(); m.coverage(plan,'detected; not yet verified')
            if args.command=='discover':
                save(RUNTIME/'discovery.json',plan); return 0
            m.isolated_test(plan)
            if args.command=='test':
                print('Isolated UDP/TCP and two-client header diagnostics passed for each proxy'); return 0
            if load(INSTALL/'desired.json').get('enabled'):
                raise Failure('Existing installation enabled; disable it before a new trial')
            INSTALL.mkdir(parents=True,mode=0o700,exist_ok=True)
            for relative in ['v2.py','controller.py','manifest.json','bin/dnscrypt-proxy']:
                src=m.package/relative; dst=INSTALL/relative
                if src.resolve()!=dst.resolve(): atomic_write(dst,src.read_bytes(),0o755 if relative.startswith('bin/') else 0o600)
            unit=f'''[Unit]\nDescription=External NextDNS device-name integration v2\nAfter=network-online.target udapi-server.service\nWants=network-online.target\n[Service]\nType=simple\nExecStart=/usr/bin/python3 {INSTALL}/v2.py manager\nExecStopPost=/usr/bin/python3 {INSTALL}/v2.py recover\nTimeoutStopSec=300\nRestart=no\n[Install]\nWantedBy=multi-user.target\n'''
            atomic_write(UNIT,unit,0o644)
            save(INSTALL/'desired.json',{'enabled':True,'committed':False,'deadline':int(time.time())+300})
            save(RUNTIME/'state.json',{'active':False,'stage':'prepared','managed':plan['forwarders'],'proxies':plan['proxies']})
            run(['systemctl','daemon-reload']); run(['systemctl','start',SERVICE])
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            state=load(RUNTIME/'state.json')
            if state.get('active'):
                m.coverage(state['plan'],'ENABLED: listener/configuration checks passed; LAN attribution needs client probe')
                print('Five-minute trial is running. Verify NextDNS and UniFi cloud access, then run sh commit.sh.',flush=True)
                return 0
            if state.get('stage') in ['stock','recovery_failed']:
                raise Failure('Activation failed: '+str(state.get('reason')))
            time.sleep(1)
        raise Failure('Activation not ready; do not commit. Trial deadline remains in effect.')
    except (Failure,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        print('ERROR: '+str(exc),file=sys.stderr); return 1


if __name__=='__main__':
    sys.exit(main())
