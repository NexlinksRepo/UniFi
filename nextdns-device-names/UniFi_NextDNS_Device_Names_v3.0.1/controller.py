#!/usr/bin/env python3
"""UniFi NextDNS device-name trial, health checks and reversible runtime install.

Requires Python 3.11+. trial/update/commit/rollback modify production DNS. test
uses an isolated loopback listener while the stock DNS processes remain running.
"""
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
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import unicodedata

try:
    import fcntl
except ImportError:  # Allows the pure and transaction tests on Windows.
    fcntl = None

SERVICE = 'nextdns-device-names.service'
LOCAL_CHECK_SECONDS = 20
NETWORK_CHECK_SECONDS = 300
UPDATE_GUARD = 'nextdns-device-names-update-guard'
DROPIN = '# nextdns-device-names managed file v1\nno-resolv\nstrip-subnet\nstrip-mac\nadd-subnet=32,128\nadd-mac\n'
WAN_BEGIN = '# nextdns-device-names WAN metadata begin v1'
WAN_END = '# nextdns-device-names WAN metadata end v1'
WAN_BLOCK = WAN_BEGIN + '\n' + '\n'.join(DROPIN.splitlines()[1:]) + '\nserver=127.0.0.1#5053\n' + WAN_END + '\n'
UNIFI_SQL = """BEGIN READ ONLY; SET LOCAL statement_timeout='1500ms';
SELECT COALESCE(json_agg(t), '[]'::json) FROM (
 SELECT lower(mac) AS mac,
 COALESCE(NULLIF(btrim(name),''), NULLIF(btrim(hostname),''),
          NULLIF(btrim(dynamic_part->>'device_name'),'')) AS name,
 CASE WHEN use_fixed_ip THEN fixed_ip ELSE NULLIF(dynamic_part->>'last_ip','') END AS ip
 FROM config.user_client WHERE mac IS NOT NULL
) t; ROLLBACK;"""


class Failure(RuntimeError):
    pass


def remove_wan_block(text):
    """Remove our complete block without overwriting later native/user edits."""
    if WAN_BEGIN not in text and WAN_END not in text:
        return text
    if text.count(WAN_BEGIN) != 1 or text.count(WAN_END) != 1:
        raise Failure('A WAN metadata block is incomplete or duplicated.')
    prefix, rest = text.split(WAN_BEGIN, 1)
    block, suffix = rest.split(WAN_END, 1)
    if prefix and not prefix.endswith('\n'):
        raise Failure('Unexpected WAN metadata marker position.')
    # Ignore only our exact directives; an edited block needs manual attention.
    if WAN_BEGIN + block + WAN_END + '\n' != WAN_BLOCK:
        raise Failure('A WAN metadata block was changed; refusing to remove other settings.')
    if suffix.startswith('\n'):
        suffix = suffix[1:]
    return prefix + suffix


def atomic_write(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else value.encode()
    fd, temporary = tempfile.mkstemp(prefix='.ndn-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def good_name(name):
    return (isinstance(name, str) and bool(name) and name == name.strip()
            and len(name.encode('utf-8')) <= 256
            and not any(unicodedata.category(c) == 'Cc' for c in name))


def normalized_mac(value):
    value = str(value or '').lower()
    return value if re.fullmatch(r'[0-9a-f]{2}(?::[0-9a-f]{2}){5}', value) else None


def client_ip(value):
    try:
        ip = ipaddress.ip_address(value)
        return str(ip) if not (ip.is_unspecified or ip.is_multicast or ip.is_loopback) else None
    except (ValueError, TypeError):
        return None


def lease_records(text, now=None):
    now = int(time.time()) if now is None else now
    records = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or not fields[0].isdigit():
            continue
        expiry, mac, ip, name = fields[:4]
        if int(expiry) != 0 and int(expiry) <= now:
            continue
        if normalized_mac(mac) and client_ip(ip):
            records.append({'mac': mac.lower(), 'ip': str(ipaddress.ip_address(ip)),
                            'name': name if name != '*' and good_name(name) else None})
    return records


def make_registry(profile, leases, unifi, overrides=None, now=None, neighbors=None,
                  gateway_ips=None, gateway_name=None):
    now = int(time.time()) if now is None else now
    by_mac, by_ip = {}, {}

    def entry(name, mac, ip):
        stable = mac or ip
        ident = base64.b32encode(hashlib.sha256((profile + ':' + stable).encode()).digest()).decode()[:8]
        return {'name': name, 'id': ident, 'mac': mac or ''}

    for record in leases + unifi:  # UniFi display names take precedence.
        mac, ip, name = normalized_mac(record.get('mac')), client_ip(record.get('ip')), record.get('name')
        if good_name(name) and (mac or ip):
            item = entry(name, mac, ip)
            if mac:
                by_mac[mac] = item
            if ip:
                by_ip[ip] = item
    for record in leases:
        if record['mac'] in by_mac:
            by_ip[record['ip']] = by_mac[record['mac']]
    # Live neighbor entries cover static clients and IPv6 addresses without a
    # DHCP lease. A current DHCP assignment wins over a conflicting stale entry.
    leased_ips = {record['ip'] for record in leases}
    for neighbor in neighbors or []:
        ip, mac = client_ip(neighbor.get('dst')), normalized_mac(neighbor.get('lladdr'))
        states = neighbor.get('state', [])
        if isinstance(states, str):
            states = [states]
        if not ip or mac not in by_mac or not set(states).intersection({'REACHABLE', 'STALE', 'DELAY', 'PROBE', 'PERMANENT', 'NOARP'}):
            continue
        if ip in leased_ips and ip in by_ip and by_ip[ip]['mac'] != mac:
            continue
        by_ip[ip] = by_mac[mac]
    if good_name(gateway_name):
        gateway = entry(gateway_name, None, 'gateway')
        for address in gateway_ips or []:
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError:
                continue
            by_ip[address] = gateway
    for kind, changes in (overrides or {}).items():
        if kind not in ('by_mac', 'by_ip') or not isinstance(changes, dict):
            raise Failure('Name overrides must contain by_mac/by_ip objects.')
        for key, name in changes.items():
            normalized = normalized_mac(key) if kind == 'by_mac' else client_ip(key)
            if not normalized or not good_name(name):
                raise Failure('Invalid IP, MAC or device name in name-overrides.json.')
            if kind == 'by_mac':
                by_mac[normalized] = entry(name, normalized, None)
                for ip, item in list(by_ip.items()):
                    if item['mac'] == normalized:
                        by_ip[ip] = by_mac[normalized]
            else:
                mac = by_ip.get(normalized, {}).get('mac')
                by_ip[normalized] = entry(name, mac, normalized)
                if mac:
                    by_mac[mac] = by_ip[normalized]
    return {'version': 1, 'enabled': True, 'expires_unix': now + 90,
            'by_ip': by_ip, 'by_mac': by_mac}


def decode_stamp(value):
    if not isinstance(value, str) or not value.startswith('sdns://'):
        raise Failure('Expected a DNS stamp.')
    try:
        encoded = value[7:]
        data = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
        if len(data) < 10 or data[0] != 2:
            raise ValueError('not a DoH stamp')
        pos = 9

        def lp():
            nonlocal pos
            length = data[pos]
            pos += 1
            result = data[pos:pos + length]
            pos += length
            if len(result) != length:
                raise ValueError('truncated stamp')
            return result.decode('ascii')

        lp()  # bootstrap address
        while True:  # certificate hashes use VLP, high bit means another hash.
            length = data[pos]
            pos += 1 + (length & 0x7f)
            if not length & 0x80:
                break
        host, url_path = lp(), lp()
        host = host.lower()
        if ':' in host or not (host == 'dns.nextdns.io' or host.endswith('.dns.nextdns.io')):
            raise ValueError('not the supported NextDNS hostname')
        profile = url_path.strip('/').split('/')[0]
        if not re.fullmatch(r'[0-9a-fA-F]{6}', profile):
            raise ValueError('profile is not a six-character ID')
        return host, profile.lower()
    except (ValueError, IndexError, UnicodeError) as exc:
        raise Failure('Unsupported NextDNS DoH stamp: ' + str(exc)) from exc


def checked_config(text):
    config = tomllib.loads(text)
    if config.get('listen_addresses') != ['127.0.0.1:5053'] or config.get('cache', False):
        raise Failure('This package requires the inspected loopback listener and cache=false.')
    names = config.get('server_names', [])
    if len(names) != 1:
        raise Failure('Expected one native NextDNS resolver.')
    try:
        stamp = config['static'][names[0]]['stamp']
    except KeyError as exc:
        raise Failure('The selected resolver must use a static NextDNS stamp.') from exc
    host, profile = decode_stamp(stamp)
    if config.get('user_name') or config.get('edns_client_subnet') or config.get('query_meta'):
        raise Failure('A privilege-drop or existing EDNS metadata configuration needs separate review.')
    return config, host, profile


def dns_packet(name, ip=None, mac=None, query_id=None):
    query_id = secrets.randbelow(65536) if query_id is None else query_id
    question = b''.join(bytes([len(label)]) + label.encode('ascii') for label in name.rstrip('.').split('.')) + b'\0' + struct.pack('!HH', 1, 1)
    options = b''
    if ip:
        address = ipaddress.ip_address(ip)
        body = struct.pack('!HBB', 1 if address.version == 4 else 2, address.max_prefixlen, 0) + address.packed
        options += struct.pack('!HH', 8, len(body)) + body
    if mac:
        body = bytes.fromhex(mac.replace(':', ''))
        options += struct.pack('!HH', 0xfde9, len(body)) + body
    additional = b'\0' + struct.pack('!HHIH', 41, 1232, 0, len(options)) + options if options else b''
    return struct.pack('!HHHHHH', query_id, 0x100, 1, 0, 0, int(bool(options))) + question + additional


def dns_exchange(host, port, name, ip=None, mac=None, tcp=False, timeout=2):
    packet = dns_packet(name, ip, mac)
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        if tcp:
            sock.sendall(struct.pack('!H', len(packet)) + packet)

            def exact(length):
                out = b''
                while len(out) < length:
                    part = sock.recv(length - len(out))
                    if not part:
                        raise Failure('Truncated TCP DNS response.')
                    out += part
                return out

            response = exact(struct.unpack('!H', exact(2))[0])
        else:
            sock.send(packet)
            response = sock.recv(65535)
    if len(response) < 12 or response[:2] != packet[:2]:
        raise Failure('Invalid DNS transaction response.')
    flags = struct.unpack('!H', response[2:4])[0]
    if not flags & 0x8000 or flags & 0xf not in (0, 3) or flags & 0x200:
        raise Failure('DNS failed, returned SERVFAIL/REFUSED, or was truncated.')
    return response


def check_tcp_listener(host, port, timeout=2):
    """Check listener readiness without sending a DNS question or other payload."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        raise Failure('DNS TCP listener is unavailable: ' + host + ':' + str(port)) from exc


class Controller:
    def __init__(self, package=None, runtime=None, install=None):
        self.package = Path(package or Path(__file__).resolve().parent)
        self.runtime = Path(runtime or '/run/nextdns-device-names')
        self.install = Path(install or '/data/nextdns-device-names')
        self.native = Path('/usr/sbin/dnscrypt-proxy')
        self.config = Path('/run/dnscrypt-proxy-doh-0.toml')
        self.dns_config = Path('/run/dnsmasq.dns.conf.d/main.conf')
        self.dhcp_dir = Path('/run/dnsmasq.dhcp.conf.d')
        self.dropin = self.dhcp_dir / 'zz-nextdns-device-names.conf'
        self.lease_file = Path('/run/dnsmasq.lease')
        self.unit = Path('/run/systemd/system') / SERVICE
        self.state_file = self.runtime / 'state.json'
        self.manifest = json.loads((self.package / 'manifest.json').read_text())

    def run(self, args, timeout=10, check=True):
        result = subprocess.run([str(a) for a in args], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
        if check and result.returncode:
            # Avoid logging native configuration or database rows.
            raise Failure(f'{Path(str(args[0])).name} failed (exit {result.returncode}).')
        return result

    @contextlib.contextmanager
    def lock(self):
        self.runtime.mkdir(mode=0o755, parents=True, exist_ok=True)
        with open(self.runtime / 'lock', 'a') as stream:
            if fcntl:
                fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def load(self):
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {}

    def save(self, state):
        atomic_write(self.state_file, json.dumps(state, indent=2) + '\n')

    def processes(self, kind):
        found = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                argv = [s.decode() for s in (proc / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
                status = (proc / 'status').read_text()
                ppid = int(re.search(r'^PPid:\s+(\d+)', status, re.M)[1])
                if kind == 'proxy' and argv == [str(self.native), '-config', str(self.config)]:
                    found.append({'pid': int(proc.name), 'ppid': ppid, 'argv': argv})
                elif (kind == 'dnsmasq' or kind.startswith('wan:')) and argv and Path(argv[0]).name == 'dnsmasq':
                    name = 'main' if kind == 'dnsmasq' else kind.split(':', 1)[1]
                    conf = self.dns_config if kind == 'dnsmasq' else self.dns_config.parent / (name + '.conf')
                    if '--conf-file=' + str(conf) not in argv:
                        continue
                    # dnsmasq has a helper child with the same argv; use its pid file.
                    pid = int(Path('/run/dnsmasq-' + name + '.pid').read_text().strip())
                    if int(proc.name) == pid:
                        found.append({'pid': pid, 'ppid': ppid, 'argv': argv})
            except (OSError, ValueError, UnicodeError, TypeError):
                continue
        return found

    def plan_wans(self):
        """Inspect only the native WAN forwarders, whose upstream is main DNS."""
        plans = []
        for file in sorted(self.dns_config.parent.glob('*.conf')):
            if file == self.dns_config:
                continue
            text = file.read_text()
            port = re.findall(r'^port=(\d+)$', text, re.M)
            if len(port) != 1 or int(port[0]) not in (20201, 20202):
                raise Failure('An unreviewed additional DNS instance needs review.')
            if not re.fullmatch(r'eth\d+', file.stem):
                raise Failure('An unreviewed WAN DNS interface needs review.')
            if WAN_BEGIN in text or WAN_END in text:
                raise Failure('WAN metadata settings already exist.')
            for line in text.splitlines():
                if line.strip().startswith(('server=', 'resolv-file=', 'conf-file=', 'conf-dir=',
                                            'no-resolv', 'add-mac', 'add-subnet', 'strip-mac', 'strip-subnet')):
                    raise Failure('WAN DNS upstream/metadata settings need review.')
            if not re.search(r'^conntrack$', text, re.M) or not re.search(r'^connmark-allowlist=', text, re.M):
                raise Failure('The expected WAN DNS policy-routing settings were not found.')
            kind = 'wan:' + file.stem
            processes = self.processes(kind)
            if len(processes) != 1:
                raise Failure('The native WAN DNS process is missing or duplicated.')
            parent = Path('/proc') / str(processes[0]['ppid']) / 'comm'
            if not parent.read_text().strip().startswith('ubios-udapi-ser'):
                raise Failure('The expected WAN DNS supervisor was not found.')
            if not text.endswith('\n'):
                raise Failure('The native WAN DNS file lacks its expected final newline.')
            plans.append({'path': str(file), 'kind': kind, 'port': int(port[0]),
                          'original_sha256': digest(file), 'process': processes[0]})
        if {p['port'] for p in plans} != {20201, 20202}:
            raise Failure('The inspected two-WAN DNS layout was not found.')
        resolvers = re.findall(r'^nameserver\s+(\S+)', Path('/etc/resolv.conf').read_text(), re.M)
        if resolvers != ['127.0.0.1']:
            raise Failure('WAN DNS is not using the inspected local main resolver.')
        return plans

    def enable_wans(self, state):
        plans = self.plan_wans()
        state['wan_dns'] = plans
        for plan in plans:
            state['processes'][plan['kind']] = [plan['process']]
        # Recovery knows all affected files/processes before the first mutation.
        state['wan_intent'] = True
        self.save(state)
        for plan in plans:
            file = Path(plan['path'])
            if digest(file) != plan['original_sha256']:
                raise Failure('UniFi changed WAN DNS configuration during installation.')
            atomic_write(file, file.read_text() + WAN_BLOCK, 0o644)
            plan['active_sha256'] = digest(file)
            self.save(state)
            self.run(plan['process']['argv'] + ['--test'])
        for plan in plans:
            self.restart(plan['kind'], state)

    def mounted(self):
        target = str(self.native)
        return any(line.split()[4].replace('\\040', ' ') == target
                   for line in Path('/proc/self/mountinfo').read_text().splitlines())

    def config_hashes(self):
        paths = [self.config, self.dns_config]
        paths += [p for p in self.dhcp_dir.iterdir() if p.is_file() and p != self.dropin]
        return {str(p): digest(p) for p in sorted(paths)}

    def frontends(self):
        interfaces = set(re.findall(r'^interface=(\S+)$', self.dns_config.read_text(), re.M))
        info = json.loads(self.run(['ip', '-j', '-4', 'addr', 'show']).stdout)
        hosts = [a['local'] for item in info if item['ifname'] in interfaces
                 for a in item.get('addr_info', []) if a.get('scope') == 'global']
        if not hosts:
            raise Failure('No LAN IPv4 DNS listener was found.')
        return hosts

    def preflight(self, active=False):
        if sys.platform != 'linux' or os.geteuid() != 0 or platform.machine() != 'aarch64':
            raise Failure('Run this package as root on the inspected ARM64 UniFi gateway.')
        for command in ('mount', 'umount', 'systemctl', 'ip', 'python3'):
            if not shutil.which(command):
                raise Failure('Missing command: ' + command)
        if self.native.is_symlink() or not self.native.is_file():
            raise Failure('Unexpected native proxy path.')
        expected = self.manifest['candidate_sha256'] if active else self.manifest['native_sha256']
        if digest(self.native) != expected:
            raise Failure('Native binary differs from the inspected build; no changes made.')
        binary = self.package / 'bin/dnscrypt-proxy'
        if digest(binary) != self.manifest['candidate_sha256']:
            raise Failure('Candidate binary checksum mismatch.')
        with binary.open('rb') as stream:
            elf = stream.read(20)
        if elf[:4] != b'\x7fELF' or struct.unpack('<H', elf[18:20])[0] != 183:
            raise Failure('Candidate is not a Linux ARM64 ELF binary.')
        _, _, profile = checked_config(self.config.read_text())
        # This integration sends EDNS client data only into the inspected local
        # NextDNS proxy. Refuse conditional/public DNS upstreams.
        for file in [self.dns_config] + [p for p in self.dhcp_dir.iterdir() if p.is_file() and p != self.dropin]:
            for line in file.read_text().splitlines():
                line = line.strip()
                if line.startswith(('conf-file=', 'conf-dir=', 'resolv-file=')):
                    raise Failure('An additional DNS include needs review before applying metadata.')
                if line.startswith('server=') and line != 'server=127.0.0.1#5053':
                    raise Failure('A non-NextDNS upstream needs review before applying metadata.')
                if line.startswith(('add-mac', 'add-subnet', 'strip-mac', 'strip-subnet')):
                    raise Failure('Existing EDNS client metadata settings need review.')
        if not active and (self.mounted() or self.dropin.exists()):
            raise Failure('A mount or metadata drop-in already exists; refusing to overwrite it.')
        processes = {kind: self.processes(kind) for kind in ('proxy', 'dnsmasq')}
        if any(len(items) != 1 for items in processes.values()):
            raise Failure('The native DNS process layout has changed.')
        for items in processes.values():
            parent = Path('/proc') / str(items[0]['ppid']) / 'comm'
            if not parent.read_text().strip().startswith('ubios-udapi-ser'):
                raise Failure('The expected UniFi DNS supervisor was not found.')
        if not active:
            self.plan_wans()
        return profile, processes, self.frontends()

    def collect(self, profile, directory=None):
        directory = directory or self.runtime
        leases = lease_records(self.lease_file.read_text())
        unifi, source = [], 'dhcp'
        try:
            result = self.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-q', '-At',
                               '-p', '5434', '-d', 'unifi-network', '-v', 'ON_ERROR_STOP=1', '-c', UNIFI_SQL], timeout=4)
            unifi = json.loads(result.stdout)
            if not isinstance(unifi, list):
                raise ValueError('invalid client records')
            source = 'unifi+dhcp'
        except (Failure, OSError, ValueError, subprocess.TimeoutExpired):
            pass
        overrides_path = self.install / 'name-overrides.json'
        overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
        try:
            neighbors = json.loads(self.run(['ip', '-j', 'neigh', 'show']).stdout)
        except (Failure, OSError, ValueError, subprocess.TimeoutExpired):
            neighbors = []
        gateway_ips = self.frontends() + ['127.0.0.1', '::1']
        gateway_name = (socket.gethostname().strip() or 'UniFi') + ' (Gateway)'
        registry = make_registry(profile, leases, unifi, overrides, neighbors=neighbors,
                                 gateway_ips=gateway_ips, gateway_name=gateway_name)
        if not registry['by_ip']:
            raise Failure('No named LAN clients are available.')
        atomic_write(Path(directory) / 'devices.json', json.dumps(registry), 0o600)
        return registry, source

    def probe_devices(self, registry, directory, port=5053):
        selected, used = [], set()
        for ip, item in registry['by_ip'].items():
            if item['id'] not in used:
                used.add(item['id'])
                selected.append((ip, item))
            if len(selected) >= 2:
                break
        if len(selected) < 2:
            raise Failure('Two named clients are required to test separate device attribution.')
        proof_path = Path(directory) / 'proof.json'
        for ip, item in selected:
            name = 'ndn-check-' + secrets.token_hex(8) + '.example.com'
            dns_exchange('127.0.0.1', port, name, ip, item.get('mac') or None)
            proof = json.loads(proof_path.read_text())
            wanted = hashlib.sha256(name.encode()).hexdigest()
            if proof.get('query_sha256') != wanted or proof.get('device_name') != item['name'] or proof.get('device_id') != item['id']:
                raise Failure('Per-device HTTP header proof did not match the requested client.')

    def isolated_test(self, profile):
        # This directory, listener and child belong only to this test.
        directory = Path(tempfile.mkdtemp(prefix='ndn-test-', dir=self.runtime))
        child = None
        try:
            registry, source = self.collect(profile, directory)
            text = self.config.read_text()
            text, count = re.subn(r'(?m)^listen_addresses\s*=.*$', "listen_addresses = ['127.0.0.1:15953']", text)
            if count != 1:
                raise Failure('Could not isolate the test listener.')
            index = 0

            def local_log(match):
                nonlocal index
                index += 1
                return match[1] + "'" + str(directory / ('proxy-' + str(index) + '.log')) + "'"

            text = re.sub(r'(?m)^(\s*(?:log_file|file)\s*=\s*)[\'\"].*[\'\"]\s*$', local_log, text)
            atomic_write(directory / 'proxy.toml', text)
            env = dict(os.environ, NEXTDNS_DEVICE_NAMES_FILE=str(directory / 'devices.json'))
            self.run([self.package / 'bin/dnscrypt-proxy', '-config', directory / 'proxy.toml', '-check'])
            with open(directory / 'startup.log', 'wb') as output:
                child = subprocess.Popen([str(self.package / 'bin/dnscrypt-proxy'), '-config', str(directory / 'proxy.toml'), '-netprobe-timeout', '5'],
                                         env=env, stdout=output, stderr=output, start_new_session=True)
                deadline = time.monotonic() + 18
                while True:
                    if child.poll() is not None:
                        raise Failure('Isolated candidate exited; see its startup.log in ' + str(directory))
                    try:
                        dns_exchange('127.0.0.1', 15953, 'example.com')
                        break
                    except (OSError, Failure):
                        if time.monotonic() >= deadline:
                            raise Failure('Isolated candidate did not become ready.')
                        time.sleep(0.25)
                dns_exchange('127.0.0.1', 15953, 'example.com', tcp=True)
                self.probe_devices(registry, directory, 15953)
            return {'passed': True, 'name_source': source, 'tested_clients': 2,
                    'udp': True, 'tcp': True, 'test_directory': str(directory)}
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)

    def stage(self):
        self.install.mkdir(parents=True, mode=0o755, exist_ok=True)
        for relative in ('controller.py', 'manifest.json', 'bin/dnscrypt-proxy'):
            source, target = self.package / relative, self.install / relative
            if source.resolve() != target.resolve():
                atomic_write(target, source.read_bytes(), 0o755 if relative.startswith('bin/') else 0o644)
        return Controller(self.install)

    def start_watchdog(self):
        unit = f'''[Unit]
Description=NextDNS device names trial and automatic recovery
After=udapi-server.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 {self.install}/controller.py watchdog
ExecStopPost=/usr/bin/python3 {self.install}/controller.py recover
Restart=no
TimeoutStopSec=60
'''
        atomic_write(self.unit, unit, 0o644)
        self.run(['systemctl', 'daemon-reload'])
        self.run(['systemctl', 'start', SERVICE])
        self.run(['systemctl', 'is-active', '--quiet', SERVICE])

    def restart(self, kind, state, rescue=False):
        old = self.processes(kind)
        for proc in old:
            os.kill(proc['pid'], signal.SIGTERM)
        old_ids = {p['pid'] for p in old}
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = self.processes(kind)
            if len(current) == 1 and current[0]['pid'] not in old_ids:
                return
            time.sleep(0.2)
        if rescue and not self.processes(kind):
            with open(self.runtime / ('rescue-' + kind + '.log'), 'ab') as log:
                subprocess.Popen(state['processes'][kind][0]['argv'], stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if len(self.processes(kind)) == 1:
                    return
                time.sleep(0.2)
        raise Failure('UniFi did not restart ' + kind + ' within the allowed time.')

    def detach_proxy(self):
        if not self.mounted():
            return
        if digest(self.native) != self.manifest['candidate_sha256']:
            raise Failure('Refusing to detach an unexpected mount over the proxy.')
        result = self.run(['umount', self.native], check=False)
        if result.returncode:
            if 'busy' not in result.stderr.lower():
                raise Failure('Could not remove the proxy mount: ' + result.stderr.strip())
            # A running executable holds its bind mount busy. Lazy detach makes
            # the stock file visible immediately; the old inode is released when
            # the supervised proxy is restarted immediately afterward.
            self.run(['umount', '--lazy', self.native])
        if self.mounted():
            raise Failure('The temporary proxy mount is still present.')

    def activate(self, state):
        # Record intent before each mutation. ExecStopPost can recover after a
        # killed installer, lost SSH session or watchdog failure.
        self.save(state)
        try:
            state['watchdog'] = True
            self.save(state)
            self.start_watchdog()
            state['mount_intent'] = True
            self.save(state)
            self.run(['mount', '--bind', self.package / 'bin/dnscrypt-proxy', self.native])
            state['dropin_intent'] = True
            self.save(state)
            atomic_write(self.dropin, DROPIN, 0o644)
            self.run(state['processes']['dnsmasq'][0]['argv'] + ['--test'])
            state['stage'] = 'restarting'
            self.save(state)
            self.restart('proxy', state)
            self.restart('dnsmasq', state)
            self.enable_wans(state)
            self.verify(state)
            state['stage'] = 'active'
            state['active'] = True
            state['next_network_check_unix'] = int(time.time()) + NETWORK_CHECK_SECONDS
            self.save(state)
        except BaseException:
            self.rollback_locked(state, 'Installation or initial validation failed')
            raise

    def verify(self, state, network=True):
        if not self.mounted() or digest(self.native) != self.manifest['candidate_sha256']:
            raise Failure('The candidate mount was lost or the proxy binary changed.')
        if not self.dropin.exists() or self.dropin.read_text() != DROPIN:
            raise Failure('UniFi removed or changed the metadata settings.')
        if self.config_hashes() != state['config_hashes']:
            raise Failure('UniFi regenerated DNS configuration; returning to stock DNS.')
        for kind in ('proxy', 'dnsmasq'):
            if len(self.processes(kind)) != 1:
                raise Failure('A DNS process is missing or duplicated: ' + kind)
        for plan in state.get('wan_dns', []):
            file = Path(plan['path'])
            if not file.exists() or digest(file) != plan.get('active_sha256'):
                raise Failure('UniFi regenerated WAN DNS configuration; returning to stock DNS.')
            if len(self.processes(plan['kind'])) != 1:
                raise Failure('A WAN DNS process is missing or duplicated.')
        registry, source = self.collect(state['profile'])
        if network:
            check_tcp_listener('127.0.0.1', 5053)
            for frontend in state['frontends']:
                check_tcp_listener(frontend, 53)
                for plan in state.get('wan_dns', []):
                    check_tcp_listener(frontend, plan['port'])
        return {'passed': True, 'name_source': source, 'tested_clients': 0,
                'lan_listeners': len(state['frontends']), 'check_mode': 'listeners' if network else 'local',
                'wan_listeners': len(state.get('wan_dns', [])),
                'named_ips': len(registry['by_ip']), 'named_macs': len(registry['by_mac'])}

    def diagnose(self, state):
        """Send diagnostic DNS questions only for an explicit test.sh command."""
        result = self.verify(state)
        registry = json.loads((self.runtime / 'devices.json').read_text())
        self.probe_devices(registry, self.runtime)
        for frontend in state['frontends']:
            for tcp in (False, True):
                dns_exchange(frontend, 53, 'example.com', tcp=tcp)
        for plan in state.get('wan_dns', []):
            for tcp in (False, True):
                dns_exchange(state['frontends'][0], plan['port'], 'example.com', tcp=tcp)
        return dict(result, tested_clients=2, check_mode='explicit_dns_diagnostic')

    def rollback_locked(self, state, reason):
        if not state or state.get('stage') == 'rolled_back':
            return {'restored': True, 'already_stock': True}
        errors = []
        # Disable identity first, then remove only our own configuration file.
        try:
            atomic_write(self.runtime / 'devices.json', '{"version":1,"enabled":false}')
        except OSError:
            # A full runtime filesystem must not prevent recovery. Removing the
            # registry also disables names after the short in-process refresh.
            try:
                (self.runtime / 'devices.json').unlink(missing_ok=True)
            except OSError as exc:
                errors.append('Could not disable the registry: ' + str(exc))
        if state.get('dropin_intent') and self.dropin.exists():
            # This is our reserved file. Remove our directives even if another
            # writer appended comments/options, preserving unrelated additions.
            managed = {'no-resolv', 'strip-subnet', 'strip-mac', 'add-subnet', 'add-mac'}
            remainder = [line for line in self.dropin.read_text().splitlines()
                         if line.split('=', 1)[0].strip() not in managed
                         and line != '# nextdns-device-names managed file v1']
            if any(line.strip() for line in remainder):
                atomic_write(self.dropin, '\n'.join(remainder) + '\n', 0o644)
            else:
                self.dropin.unlink()
        # Stop every edge forwarder from adding identity before stock returns.
        # The patched proxy continues to strip metadata during this transition.
        metadata_stopped = True
        for plan in state.get('wan_dns', []) if state.get('wan_intent') else []:
            try:
                file = Path(plan['path'])
                if file.exists():
                    before = file.read_text()
                    after = remove_wan_block(before)
                    if before != after:
                        atomic_write(file, after, 0o644)
            except Exception as exc:
                metadata_stopped = False
                errors.append(str(exc))
        for kind in [p['kind'] for p in state.get('wan_dns', [])] + ['dnsmasq']:
            try:
                self.restart(kind, state, rescue=True)
            except Exception as exc:
                metadata_stopped = False
                errors.append(str(exc))
        if state.get('mount_intent') and metadata_stopped:
            try:
                self.detach_proxy()
            except Exception as exc:
                errors.append(str(exc))
        if state.get('mount_intent') and not metadata_stopped:
            errors.append('Kept the metadata-stripping proxy mounted because dnsmasq recovery failed.')
        for kind in ('proxy',) if metadata_stopped else ():
            try:
                self.restart(kind, state, rescue=True)
            except Exception as exc:
                errors.append(str(exc))
        for frontend in state.get('frontends', []):
            for attempt in range(3):
                try:
                    check_tcp_listener(frontend, 53)
                    break
                except Exception as exc:
                    if attempt == 2:
                        errors.append('Stock DNS listener check failed: ' + str(exc))
                    else:
                        time.sleep(0.3)
        state.update(active=False, stage='rollback_failed' if errors else 'rolled_back',
                     reason=reason, rollback_errors=errors, restored_unix=int(time.time()))
        self.save(state)
        if errors:
            raise Failure('Rollback needs attention: ' + '; '.join(errors))
        return {'restored': True, 'reason': reason}

    def trial(self, seconds):
        with self.lock():
            if self.load().get('stage') not in (None, 'rolled_back'):
                raise Failure('A trial or recovery already exists; use status or rollback first.')
            profile, processes, frontends = self.preflight()
            result = self.isolated_test(profile)
            state = {'version': 1, 'stage': 'prepared', 'active': False,
                     'profile': profile, 'processes': processes, 'frontends': frontends,
                     'config_hashes': self.config_hashes(), 'deadline': int(time.time()) + seconds,
                     'committed': False, 'started_unix': int(time.time()), 'isolated_test': result}
            self.collect(profile)
            self.activate(state)
        return {'active': True, 'trial_seconds': seconds,
                'automatic_rollback_at_unix': state['deadline'],
                'commit_command': 'sh ./commit.sh', 'rollback_command': 'sh ./rollback.sh'}

    def commit(self):
        with self.lock():
            state = self.load()
            if not state.get('active'):
                raise Failure('No active trial exists.')
            if state.get('deadline') and time.time() >= state['deadline']:
                self.rollback_locked(state, 'Trial expired before commit')
                raise Failure('The trial expired and was rolled back.')
            result = self.verify(state)
            state.update(committed=True, deadline=None,
                         next_network_check_unix=int(time.time()) + NETWORK_CHECK_SECONDS)
            self.save(state)
        return {'committed': True, 'lifetime': 'until reboot or rollback', 'health_checks': result}

    def boot_id(self):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def recovery_deferred(self):
        """Allow only the bounded, same-boot monitor replacement to skip recovery."""
        try:
            marker = json.loads((self.runtime / 'monitor-handoff.json').read_text())
            remaining = marker['expires_unix'] - time.time()
            return (0 < remaining <= 90 and marker['boot_id'] == self.boot_id()
                    and marker['candidate_sha256'] == self.manifest['candidate_sha256'])
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def recover(self, force=False):
        # ExecStopPost runs while the updater holds the transaction lock. Check
        # its short handoff marker before locking, otherwise systemctl stop and
        # the updater would wait on each other. The independent timer ignores it.
        if not force and self.recovery_deferred():
            return {'recovery_deferred': True, 'reason': 'Bounded monitor update'}
        with self.lock():
            return self.rollback_locked(self.load(), 'Watchdog exited')

    def replace_watchdog(self):
        pid_text = self.run(['systemctl', 'show', '--property=MainPID', '--value', SERVICE]).stdout.strip()
        pid = int(pid_text)
        if pid <= 1 or pid == os.getpid():
            raise Failure('The running monitor PID is invalid.')
        argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
        if [a.decode() for a in argv[-2:]] != [str(self.install / 'controller.py'), 'watchdog']:
            raise Failure('The running service is not the expected monitor.')
        # The previous monitor treats SIGTERM as a rollback request. SIGKILL
        # avoids its old shutdown handler; guarded ExecStopPost handles handoff.
        os.kill(pid, signal.SIGKILL)
        self.run(['systemctl', 'stop', SERVICE], check=False, timeout=15)
        self.run(['systemctl', 'reset-failed', SERVICE], check=False)
        self.start_watchdog()

    def update(self):
        """Update the monitor in place without resetting commit or restarting DoH."""
        with self.lock():
            state = self.load()
            if not state.get('active') or state.get('stage') != 'active':
                raise Failure('Update requires an active installation; otherwise use install.sh.')
            if state.get('deadline') and time.time() >= state['deadline']:
                raise Failure('The existing trial has expired; it cannot be extended by updating.')
            self.verify(state, network=False)
            installed_manifest = json.loads((self.install / 'manifest.json').read_text())
            if installed_manifest['candidate_sha256'] != self.manifest['candidate_sha256']:
                raise Failure('This update cannot replace the mounted proxy binary.')
            if digest(self.install / 'bin/dnscrypt-proxy') != self.manifest['candidate_sha256']:
                raise Failure('The installed candidate checksum differs.')
            # Validate the migration before touching the installed monitor.
            if not state.get('wan_intent'):
                self.plan_wans()
            before = {kind: [p['pid'] for p in self.processes(kind)] for kind in ('proxy', 'dnsmasq')}
            for relative in ('controller.py', 'manifest.json'):
                source, target = self.package / relative, self.install / relative
                if source.resolve() != target.resolve():
                    atomic_write(target, source.read_bytes(), 0o644)
            # If the updater is killed, systemd performs corrected rollback from
            # the installed payload. No SSH connection is needed by this timer.
            self.run(['systemd-run', '--quiet', '--unit=' + UPDATE_GUARD,
                      '--on-active=75s', '--timer-property=AccuracySec=1s',
                      '/usr/bin/python3', self.install / 'controller.py', 'recover-force'])
            success = False
            try:
                atomic_write(self.runtime / 'monitor-handoff.json', json.dumps({
                    'boot_id': self.boot_id(), 'expires_unix': int(time.time()) + 90,
                    'candidate_sha256': self.manifest['candidate_sha256']}))
                self.replace_watchdog()
                if not state.get('wan_intent'):
                    self.enable_wans(state)
                result = self.verify(state)
                state.update(monitor_version=self.manifest['package_version'],
                             updated_unix=int(time.time()), last_check_unix=int(time.time()),
                             next_network_check_unix=int(time.time()) + NETWORK_CHECK_SECONDS,
                             consecutive_failures=0, named_ips=result.get('named_ips'),
                             named_macs=result.get('named_macs'))
                self.save(state)
                self.run(['systemctl', 'is-active', '--quiet', SERVICE])
                success = True
            except BaseException:
                self.rollback_locked(state, 'Monitor/WAN update or validation failed')
                raise
            finally:
                (self.runtime / 'monitor-handoff.json').unlink(missing_ok=True)
                if success or self.load().get('stage') == 'rolled_back':
                    self.run(['systemctl', 'stop', UPDATE_GUARD + '.timer', UPDATE_GUARD + '.service'],
                             check=False)
                    self.run(['systemctl', 'reset-failed', UPDATE_GUARD + '.service'], check=False)
            after = {kind: [p['pid'] for p in self.processes(kind)] for kind in ('proxy', 'dnsmasq')}
            return {'updated': True, 'package_version': self.manifest['package_version'],
                    'committed': state.get('committed', False), 'deadline': state.get('deadline'),
                    'main_dns_and_proxy_pids_unchanged': before == after, 'health_checks': result}

    def watchdog(self):
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        next_check, failures = 0, 0
        while not stopping:
            with self.lock():
                state = self.load()
                if not state or state.get('stage') == 'rolled_back':
                    return
                if state.get('deadline') and time.time() >= state['deadline']:
                    self.rollback_locked(state, 'Uncommitted trial expired')
                    return
                if state.get('stage') == 'active' and time.monotonic() >= next_check:
                    try:
                        network = time.time() >= state.get('next_network_check_unix', 0)
                        result = self.verify(state, network=network)
                        if network:
                            state['next_network_check_unix'] = int(time.time()) + NETWORK_CHECK_SECONDS
                        failures = 0
                        state.update(last_check_unix=int(time.time()), consecutive_failures=0,
                                     named_ips=result.get('named_ips'), named_macs=result.get('named_macs'))
                        self.save(state)
                    except Exception as exc:
                        failures += 1
                        state.update(consecutive_failures=failures, last_error=str(exc))
                        self.save(state)
                        if failures >= 2:
                            self.rollback_locked(state, 'Health checks failed twice: ' + str(exc))
                            return
                    next_check = time.monotonic() + (3 if failures else LOCAL_CHECK_SECONDS)
            time.sleep(1)
        with self.lock():
            self.rollback_locked(self.load(), 'Watchdog stopped')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'test', 'trial', 'update', 'commit', 'rollback', 'status', 'watchdog', 'recover', 'recover-force'))
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    controller = Controller()
    try:
        if args.command == 'status':
            state = controller.load()
            result = {key: state[key] for key in ('stage', 'active', 'committed', 'deadline', 'last_check_unix', 'monitor_version', 'named_ips', 'named_macs', 'last_error', 'reason', 'rollback_errors') if key in state}
            if not result:
                result = {'active': False, 'stage': 'stock'}
        elif args.command in ('recover', 'recover-force'):
            result = controller.recover(force=args.command == 'recover-force')
        elif args.command == 'update':
            result = controller.update()
        elif args.command in ('watchdog', 'rollback'):
            if args.command == 'watchdog':
                controller.watchdog()
                return 0
            with controller.lock():
                result = controller.rollback_locked(controller.load(), 'Manual rollback' if args.command == 'rollback' else 'Watchdog exited')
            if args.command == 'rollback':
                controller.run(['systemctl', 'stop', SERVICE], check=False, timeout=65)
                if controller.unit.exists():
                    controller.unit.unlink()
                controller.run(['systemctl', 'daemon-reload'])
        elif args.command == 'commit':
            controller = Controller('/data/nextdns-device-names')
            result = controller.commit()
        elif args.command == 'trial':
            if not 120 <= args.seconds <= 1800:
                raise Failure('Trial duration must be between 120 and 1800 seconds.')
            # Validate before copying anything into the installed directory.
            with controller.lock():
                controller.preflight()
                if controller.load().get('stage') not in (None, 'rolled_back'):
                    raise Failure('A trial already exists.')
                controller = controller.stage()
            result = controller.trial(args.seconds)
        else:
            with controller.lock():
                state = controller.load()
                if state.get('active'):
                    result = controller.diagnose(state) if args.command == 'test' else controller.verify(state)
                else:
                    profile, _, _ = controller.preflight()
                    result = {'passed': True, 'native_build': 'matched', 'configuration': 'matched'}
                    if args.command == 'test':
                        result = controller.isolated_test(profile)
        print(json.dumps(result, indent=2))
        return 0
    except (Failure, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    if json.loads((Path(__file__).resolve().parent / 'manifest.json').read_text()).get('package_version', '').startswith(('2.', '3.')):
        sys.exit('This is the v1 helper module. Use the versioned shell entry points or v3.py.')
    sys.exit(main())
