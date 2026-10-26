import base64
import copy
import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controller', ROOT / 'controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def stamp(host='dns.nextdns.io', profile='abcdef'):
    def lp(value):
        b = value.encode()
        return bytes([len(b)]) + b
    return 'sdns://' + base64.urlsafe_b64encode(b'\x02' + b'\x00' * 8 + lp('45.90.28.0') + b'\0' + lp(host) + lp('/' + profile)).decode().rstrip('=')


class PureTests(unittest.TestCase):
    def test_stamp(self):
        self.assertEqual(c.decode_stamp(stamp()), ('dns.nextdns.io', 'abcdef'))
        for value in ('sdns://bad', stamp('dns.nextdns.io.attacker.example'), stamp(profile='bad'), 'https://dns.nextdns.io/abcdef'):
            with self.assertRaises(c.Failure):
                c.decode_stamp(value)

    def test_stamp_multiple_certificate_hashes(self):
        lp = lambda s: bytes([len(s)]) + s
        data = b'\x02' + b'\x00' * 8 + lp(b'45.90.28.0') + b'\xa0' + b'x' * 32 + b'\x20' + b'y' * 32 + lp(b'dns.nextdns.io') + lp(b'/abcdef')
        value = 'sdns://' + base64.urlsafe_b64encode(data).decode().rstrip('=')
        self.assertEqual(c.decode_stamp(value)[1], 'abcdef')

    def test_expired_and_malformed_leases(self):
        rows = c.lease_records('100 00:11:22:33:44:55 192.168.1.5 old *\n'
                              '0 00:11:22:33:44:56 192.168.1.6 printer *\n'
                              '999999 bad-mac 192.168.1.7 bad *\n'
                              '999999 00:11:22:33:44:57 not-an-ip bad *\n'
                              'duid 00001234\n', now=200)
        self.assertEqual([r['name'] for r in rows], ['printer'])

    def test_unifi_names_preferred_and_ids_stable(self):
        leases = [{'mac': '00:11:22:33:44:55', 'ip': '192.168.1.5', 'name': 'DHCP-name'}]
        unifi = [{'mac': '00:11:22:33:44:55', 'ip': None, 'name': "Office iPhone"}]
        registry = c.make_registry('abcdef', leases, unifi, now=100)
        self.assertEqual(registry['by_ip']['192.168.1.5']['name'], 'Office iPhone')
        changed = c.make_registry('abcdef', [dict(leases[0], ip='192.168.1.6')], [dict(unifi[0], name='New name')], now=100)
        self.assertEqual(registry['by_ip']['192.168.1.5']['id'], changed['by_ip']['192.168.1.6']['id'])
        other_profile = c.make_registry('123456', leases, unifi, now=100)
        self.assertNotEqual(registry['by_ip']['192.168.1.5']['id'], other_profile['by_ip']['192.168.1.5']['id'])

    def test_neighbor_addresses_cover_static_and_ipv6_clients(self):
        unifi = [{'mac': '00:11:22:33:44:55', 'ip': None, 'name': 'Static laptop'}]
        neighbors = [{'dst': '192.168.1.90', 'lladdr': unifi[0]['mac'], 'state': ['REACHABLE']},
                     {'dst': 'fd00::90', 'lladdr': unifi[0]['mac'], 'state': ['STALE']},
                     {'dst': '192.168.1.91', 'lladdr': unifi[0]['mac'], 'state': ['FAILED']}]
        registry = c.make_registry('abcdef', [], unifi, neighbors=neighbors)
        self.assertEqual(registry['by_ip']['192.168.1.90']['name'], 'Static laptop')
        self.assertEqual(registry['by_ip']['fd00::90']['name'], 'Static laptop')
        self.assertNotIn('192.168.1.91', registry['by_ip'])

    def test_stale_neighbor_does_not_override_current_dhcp_assignment(self):
        leases = [{'mac': '00:11:22:33:44:55', 'ip': '192.168.1.5', 'name': 'Current'}]
        unifi = [{'mac': '00:11:22:33:44:66', 'ip': None, 'name': 'Previous'}]
        neighbors = [{'dst': '192.168.1.5', 'lladdr': unifi[0]['mac'], 'state': ['STALE']}]
        registry = c.make_registry('abcdef', leases, unifi, neighbors=neighbors)
        self.assertEqual(registry['by_ip']['192.168.1.5']['name'], 'Current')

    def test_gateway_gets_its_own_identity_without_relabeling_clients(self):
        leases = [{'mac': '00:11:22:33:44:55', 'ip': '192.168.1.5', 'name': 'Laptop'}]
        registry = c.make_registry('abcdef', leases, [], gateway_ips=['192.168.1.1', '127.0.0.1', '::1'], gateway_name='Core (Gateway)')
        self.assertEqual(registry['by_ip']['127.0.0.1']['name'], 'Core (Gateway)')
        self.assertEqual(registry['by_ip']['::1']['id'], registry['by_ip']['192.168.1.1']['id'])
        self.assertEqual(registry['by_ip']['192.168.1.5']['name'], 'Laptop')
        self.assertNotEqual(registry['by_ip']['192.168.1.1']['id'], registry['by_ip']['192.168.1.5']['id'])

    def test_mac_and_ip_overrides(self):
        leases = [{'mac': '00:11:22:33:44:55', 'ip': '192.168.1.5', 'name': 'DHCP'}]
        for override in ({'by_mac': {'00:11:22:33:44:55': 'Custom'}}, {'by_ip': {'192.168.1.5': 'Custom'}}):
            reg = c.make_registry('abcdef', leases, [], override, now=100)
            self.assertEqual(reg['by_ip']['192.168.1.5']['name'], 'Custom')
            self.assertEqual(reg['by_mac']['00:11:22:33:44:55']['name'], 'Custom')

    def test_override_validation(self):
        for override in ({'wrong': {}}, {'by_ip': {'192.168.1.5': 'bad\r\nHeader: injected'}}, {'by_mac': {'bad': 'name'}}):
            with self.assertRaises(c.Failure):
                c.make_registry('abcdef', [], [], override)

    def test_dns_packet_encodes_original_client(self):
        packet = c.dns_packet('ndn-check-test.example.com', '192.168.1.5', '00:11:22:33:44:55', 123)
        self.assertEqual(struct.unpack('!6H', packet[:12]), (123, 256, 1, 0, 0, 1))
        self.assertIn(b'\x00\x08\x00\x08\x00\x01\x20\x00\xc0\xa8\x01\x05', packet)
        self.assertIn(b'\xfd\xe9\x00\x06\x00\x11\x22\x33\x44\x55', packet)

    def test_dns_packet_supports_ipv6(self):
        packet = c.dns_packet('example.com', 'fd00::20')
        self.assertIn(b'\x00\x08\x00\x14\x00\x02\x80\x00', packet)

    def test_atomic_write_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'a.json'
            c.atomic_write(file, '{"first":1}')
            c.atomic_write(file, '{"second":2}')
            self.assertEqual(json.loads(file.read_text()), {'second': 2})
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['a.json'])

    def test_config_requires_expected_nextdns_layout(self):
        text = "listen_addresses=['127.0.0.1:5053']\ncache=false\nserver_names=['nextdns']\n[static.nextdns]\nstamp='" + stamp() + "'\n"
        self.assertEqual(c.checked_config(text)[2], 'abcdef')
        for bad in (text.replace('5053', '53'), text.replace('cache=false', 'cache=true'), text.replace('dns.nextdns.io', 'other')):
            if bad != text:
                with self.assertRaises((c.Failure, ValueError)):
                    c.checked_config(bad)


class FakeController(c.Controller):
    def __init__(self, root, fail=None):
        self.package = root / 'package'
        self.package.mkdir()
        self.install = self.package
        self.runtime = root / 'run'
        self.runtime.mkdir()
        self.native = root / 'native'
        self.native.write_bytes(b'stock')
        self.dropin = root / 'metadata.conf'
        self.state_file = self.runtime / 'state.json'
        self.manifest = {'candidate_sha256': c.hashlib.sha256(b'candidate').hexdigest()}
        self.bound = False
        self.calls = []
        self.fail = fail

    def run(self, args, **kwargs):
        op = 'mount' if str(args[0]) == 'mount' else 'umount' if str(args[0]) == 'umount' else 'syntax'
        self.calls.append(op)
        if op == self.fail:
            raise c.Failure('injected ' + op)
        if op == 'mount':
            self.bound = True
            self.native.write_bytes(b'candidate')
        if op == 'umount':
            self.bound = False
            self.native.write_bytes(b'stock')
        return c.subprocess.CompletedProcess(args, 0, stdout='', stderr='')

    def start_watchdog(self):
        self.calls.append('watchdog')
        if self.fail == 'watchdog':
            raise c.Failure('injected watchdog')

    def restart(self, kind, state, rescue=False):
        self.calls.append(('rescue-' if rescue else 'restart-') + kind)
        if not rescue and self.fail == 'restart-' + kind:
            raise c.Failure('injected restart failure')
        if rescue and self.fail == 'rescue-' + kind:
            raise c.Failure('injected rescue failure')

    def verify(self, state, network=True):
        self.calls.append('verify')
        if self.fail == 'verify':
            raise c.Failure('injected verify')
        return {'passed': True}

    def mounted(self):
        return self.bound

    def plan_wans(self):
        return []


class TransactionTests(unittest.TestCase):
    def state(self):
        return {'stage': 'prepared', 'active': False, 'deadline': int(time.time()) + 300,
                'processes': {'dnsmasq': [{'argv': ['dnsmasq', '--conf-file=main.conf']}]}, 'frontends': []}

    def test_every_activation_failure_restores_stock_and_removes_flags(self):
        for phase in ('watchdog', 'mount', 'syntax', 'restart-proxy', 'restart-dnsmasq', 'verify'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as folder:
                controller = FakeController(Path(folder), phase)
                with self.assertRaises(c.Failure):
                    controller.activate(self.state())
                self.assertFalse(controller.bound)
                self.assertFalse(controller.dropin.exists())
                self.assertEqual(controller.load()['stage'], 'rolled_back')
                self.assertIn('rescue-proxy', controller.calls)
                self.assertIn('rescue-dnsmasq', controller.calls)

    def test_successful_trial_can_be_rolled_back(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            self.assertTrue(controller.bound)
            self.assertTrue(controller.load()['active'])
            result = controller.rollback_locked(controller.load(), 'requested')
            self.assertTrue(result['restored'])
            self.assertFalse(controller.bound)
            self.assertEqual(controller.native.read_bytes(), b'stock')
            self.assertFalse(controller.dropin.exists())

    def test_rollback_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.rollback_locked(controller.load(), 'first')
            calls = list(controller.calls)
            self.assertTrue(controller.rollback_locked(controller.load(), 'second')['already_stock'])
            self.assertEqual(controller.calls, calls)

    def test_metadata_stops_before_stock_proxy_returns(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.calls.clear()
            controller.rollback_locked(controller.load(), 'requested')
            self.assertLess(controller.calls.index('rescue-dnsmasq'), controller.calls.index('umount'))
            self.assertLess(controller.calls.index('umount'), controller.calls.index('rescue-proxy'))

    def test_busy_running_proxy_mount_uses_lazy_detach(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            original = controller.run
            lazy_used = []
            def busy(args, **kwargs):
                if args[0] == 'umount' and '--lazy' not in args:
                    return c.subprocess.CompletedProcess(args, 32, stdout='', stderr='target is busy')
                if '--lazy' in args:
                    lazy_used.append(True)
                return original(args, **kwargs)
            controller.run = busy
            controller.rollback_locked(controller.load(), 'requested')
            self.assertEqual(lazy_used, [True])
            self.assertFalse(controller.bound)
            self.assertEqual(controller.native.read_bytes(), b'stock')

    def test_detach_refuses_unexpected_mount_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.bound = True
            with self.assertRaises(c.Failure):
                controller.detach_proxy()
            self.assertTrue(controller.bound)

    def test_watchdog_local_refresh_does_not_send_network_probes(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            observed = []
            def verify(state, network=True):
                observed.append(network)
                return {'passed': True}
            controller.verify = verify
            def finish(_):
                controller.save(dict(controller.load(), stage='rolled_back', active=False))
            with patch.object(c.signal, 'signal'), patch.object(c.time, 'sleep', side_effect=finish):
                controller.watchdog()
            self.assertEqual(observed, [False])

    def test_failed_dnsmasq_recovery_keeps_metadata_stripping_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.fail = 'rescue-dnsmasq'
            with self.assertRaises(c.Failure):
                controller.rollback_locked(controller.load(), 'requested')
            self.assertTrue(controller.bound)
            self.assertFalse(controller.dropin.exists())
            self.assertEqual(controller.load()['stage'], 'rollback_failed')

    def test_rollback_preserves_unrelated_appended_options(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.dropin.write_text(c.DROPIN + 'log-queries=extra\n# my note\n')
            controller.rollback_locked(controller.load(), 'requested')
            self.assertEqual(controller.dropin.read_text(), 'log-queries=extra\n# my note\n')
            self.assertFalse(controller.bound)

    def test_expired_trial_rolls_back_instead_of_committing(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            state = self.state()
            state['deadline'] = int(time.time()) - 1
            controller.activate(state)
            with self.assertRaises(c.Failure):
                controller.commit()
            self.assertFalse(controller.bound)

    def test_commit_clears_deadline_and_keeps_health_monitoring(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            self.assertTrue(controller.commit()['committed'])
            self.assertIsNone(controller.load()['deadline'])
            self.assertTrue(controller.load()['active'])

    def test_trial_timeout_rolls_back_without_ssh_session(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            state = self.state()
            state['deadline'] = int(time.time()) - 1
            controller.activate(state)
            with patch.object(c.signal, 'signal'):
                controller.watchdog()
            self.assertEqual(controller.load()['stage'], 'rolled_back')

    def test_watchdog_two_health_failures_trigger_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.fail = 'verify'
            ticks = iter(range(0, 1000, 100))
            with patch.object(c.signal, 'signal'), patch.object(c.time, 'sleep'), patch.object(c.time, 'monotonic', side_effect=lambda: next(ticks)):
                controller.watchdog()
            self.assertEqual(controller.load()['stage'], 'rolled_back')

    def test_rollback_reports_unmount_failure_and_still_recovers_dns(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            controller.activate(self.state())
            controller.fail = 'umount'
            with self.assertRaises(c.Failure):
                controller.rollback_locked(controller.load(), 'requested')
            self.assertFalse(controller.dropin.exists())
            self.assertIn('rescue-proxy', controller.calls)
            self.assertIn('rescue-dnsmasq', controller.calls)
            self.assertEqual(controller.load()['stage'], 'rollback_failed')

    def wan_plans(self, controller):
        plans = []
        for number, port in ((8, 20201), (9, 20202)):
            file = controller.package / ('eth%d.conf' % number)
            file.write_bytes(('interface=br0\nconntrack\nport=%d\n' % port).encode())
            plans.append({'path': str(file), 'kind': 'wan:eth%d' % number, 'port': port,
                          'original_sha256': c.digest(file),
                          'process': {'argv': ['dnsmasq', '--conf-file=' + str(file)]}})
        controller.plan_wans = lambda: plans
        return plans

    def test_wan_metadata_goes_directly_to_local_encrypted_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            plans = self.wan_plans(controller)
            originals = {p['path']: Path(p['path']).read_bytes() for p in plans}
            controller.activate(self.state())
            for plan in plans:
                text = Path(plan['path']).read_text()
                self.assertIn('no-resolv\n', text)
                self.assertIn('server=127.0.0.1#5053\n', text)
                self.assertIn('strip-subnet\nstrip-mac\nadd-subnet=32,128\nadd-mac\n', text)
                self.assertEqual(c.digest(plan['path']), plan['active_sha256'])
            controller.calls.clear()
            controller.rollback_locked(controller.load(), 'requested')
            for plan in plans:
                self.assertEqual(Path(plan['path']).read_bytes(), originals[plan['path']])
                self.assertLess(controller.calls.index('rescue-' + plan['kind']), controller.calls.index('umount'))

    def test_wan_restart_failure_rolls_back_all_modified_forwarders(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder), fail='restart-wan:eth9')
            plans = self.wan_plans(controller)
            with self.assertRaises(c.Failure):
                controller.activate(self.state())
            self.assertFalse(controller.bound)
            for plan in plans:
                self.assertNotIn(c.WAN_BEGIN, Path(plan['path']).read_text())

    def test_wan_restore_preserves_later_native_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            plans = self.wan_plans(controller)
            controller.activate(self.state())
            file = Path(plans[0]['path'])
            file.write_text(file.read_text() + '# later native change\n')
            controller.rollback_locked(controller.load(), 'requested')
            self.assertIn('# later native change\n', file.read_text())
            self.assertNotIn(c.WAN_BEGIN, file.read_text())

    def test_failed_wan_recovery_retains_metadata_stripping_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            self.wan_plans(controller)
            controller.activate(self.state())
            controller.fail = 'rescue-wan:eth9'
            with self.assertRaises(c.Failure):
                controller.rollback_locked(controller.load(), 'requested')
            self.assertTrue(controller.bound)
            self.assertNotIn('umount', controller.calls)

    def prepare_update(self, controller, committed=True):
        controller.activate(self.state())
        state = controller.load()
        state.pop('wan_intent', None)  # Simulate the installed v1.0.0 state.
        state.pop('wan_dns', None)
        state.update(committed=committed, deadline=None if committed else int(time.time()) + 100)
        controller.save(state)
        controller.manifest['package_version'] = '1.0.2'
        (controller.install / 'manifest.json').write_text(c.json.dumps(controller.manifest))
        (controller.install / 'bin').mkdir()
        (controller.install / 'bin/dnscrypt-proxy').write_bytes(b'candidate')
        controller.processes = lambda kind: [{'pid': 9001 if kind == 'proxy' else 9002}]
        controller.boot_id = lambda: 'same-boot'
        controller.replace_watchdog = lambda: controller.calls.append('replace-monitor')
        controller.calls.clear()
        return state

    def test_update_preserves_commit_and_does_not_restart_main_dns(self):
        for committed in (True, False):
            with self.subTest(committed=committed), tempfile.TemporaryDirectory() as folder:
                controller = FakeController(Path(folder))
                before = self.prepare_update(controller, committed)
                self.wan_plans(controller)
                result = controller.update()
                self.assertTrue(result['updated'])
                self.assertEqual(controller.load()['committed'], committed)
                self.assertEqual(controller.load()['deadline'], before['deadline'])
                self.assertTrue(result['main_dns_and_proxy_pids_unchanged'])
                self.assertNotIn('restart-proxy', controller.calls)
                self.assertNotIn('restart-dnsmasq', controller.calls)
                self.assertFalse((controller.runtime / 'monitor-handoff.json').exists())

    def test_failed_update_uses_corrected_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            self.prepare_update(controller)
            plans = self.wan_plans(controller)
            controller.fail = 'restart-wan:eth9'
            with self.assertRaises(c.Failure):
                controller.update()
            self.assertEqual(controller.load()['stage'], 'rolled_back')
            self.assertFalse(controller.bound)
            for plan in plans:
                self.assertNotIn(c.WAN_BEGIN, Path(plan['path']).read_text())
            self.assertFalse((controller.runtime / 'monitor-handoff.json').exists())

    def test_handoff_is_bounded_and_force_recovery_ignores_it(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            self.prepare_update(controller)
            marker = {'boot_id': 'same-boot', 'expires_unix': time.time() + 60,
                      'candidate_sha256': controller.manifest['candidate_sha256']}
            file = controller.runtime / 'monitor-handoff.json'
            c.atomic_write(file, c.json.dumps(marker))
            self.assertTrue(controller.recovery_deferred())
            self.assertTrue(controller.recover()['recovery_deferred'])
            self.assertTrue(controller.bound)
            for changes in ({'boot_id': 'other-boot'}, {'expires_unix': time.time() - 1},
                            {'expires_unix': time.time() + 1000}, {'candidate_sha256': 'wrong'}):
                c.atomic_write(file, c.json.dumps(dict(marker, **changes)))
                self.assertFalse(controller.recovery_deferred())
            c.atomic_write(file, c.json.dumps(marker))
            controller.recover(force=True)
            self.assertFalse(controller.bound)

    def test_modified_wan_block_is_not_silently_deleted(self):
        with self.assertRaises(c.Failure):
            c.remove_wan_block('native\n' + c.WAN_BLOCK.replace('add-mac', 'log-queries'))


    def test_scheduled_validation_never_sends_dns_questions(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            self.wan_plans(controller)
            state = self.state()
            state.update(profile='abcdef', config_hashes={}, frontends=['192.0.2.1', '192.0.2.2'])
            controller.activate(state)
            controller.config_hashes = lambda: {}
            controller.processes = lambda kind: [{'pid': 1001}]
            controller.collect = lambda profile: ({'by_ip': {}, 'by_mac': {}}, 'test')
            with patch.object(c, 'dns_exchange', side_effect=AssertionError('No scheduled DNS queries')) as dns, \
                 patch.object(controller, 'probe_devices', side_effect=AssertionError('No scheduled attribution probes')) as probes, \
                 patch.object(c.socket, 'create_connection') as connect:
                result = c.Controller.verify(controller, controller.load(), network=True)
                self.assertEqual(result['check_mode'], 'listeners')
                self.assertEqual(result['tested_clients'], 0)
                self.assertEqual(connect.call_count, 7)
                dns.assert_not_called()
                probes.assert_not_called()
                connect.return_value.__enter__.return_value.send.assert_not_called()
                connect.return_value.__enter__.return_value.sendall.assert_not_called()

    def test_unavailable_listener_is_reported_without_a_dns_query(self):
        with patch.object(c.socket, 'create_connection', side_effect=ConnectionRefusedError), \
             patch.object(c, 'dns_exchange') as dns:
            with self.assertRaises(c.Failure):
                c.check_tcp_listener('127.0.0.1', 5053)
            dns.assert_not_called()

    def test_rollback_checks_listeners_without_dns_questions(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            state = self.state()
            state['frontends'] = ['192.0.2.1']
            controller.activate(state)
            with patch.object(c, 'dns_exchange', side_effect=AssertionError('No rollback DNS queries')) as dns, \
                 patch.object(c.socket, 'create_connection') as connect:
                self.assertTrue(controller.rollback_locked(controller.load(), 'requested')['restored'])
                connect.assert_called_once_with(('192.0.2.1', 53), timeout=2)
                dns.assert_not_called()

    def test_full_dns_diagnostic_remains_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            state = self.state()
            state['frontends'] = ['192.0.2.1']
            c.atomic_write(controller.runtime / 'devices.json', '{"by_ip":{},"by_mac":{}}')
            with patch.object(controller, 'probe_devices') as probes, patch.object(c, 'dns_exchange') as dns:
                result = controller.diagnose(state)
                self.assertEqual(result['check_mode'], 'explicit_dns_diagnostic')
                probes.assert_called_once()
                self.assertEqual(dns.call_count, 2)

    def test_monitor_only_update_leaves_all_dns_processes_running(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController(Path(folder))
            before = self.prepare_update(controller)
            self.wan_plans(controller)
            controller.enable_wans(before)
            controller.calls.clear()
            result = controller.update()
            self.assertTrue(result['committed'])
            self.assertEqual(result['deadline'], before['deadline'])
            self.assertTrue(result['main_dns_and_proxy_pids_unchanged'])
            self.assertFalse(any(call.startswith(('restart-', 'rescue-')) for call in controller.calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
