#!/usr/bin/env python3
"""Optional two-terminal test of the LAN forwarding path without production cutover.

Run on the gateway, then run probe-client.py --port 15954 on a LAN computer.
Both the temporary dnsmasq and proxy are stopped when the test ends.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controller', ROOT / 'controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class LANController(c.Controller):
    def probe_devices(self, registry, directory, port=5053):
        super().probe_devices(registry, directory, port)
        proof_file = Path(directory) / 'proof.json'
        initial = json.loads(proof_file.read_text())['query_sha256']
        hosts = self.frontends()
        # Preserve vendor-specific interface/socket setup, but use separate
        # files, ports and pid. Do not include any production DHCP configuration.
        lab_config = Path(directory) / 'lab-main.conf'
        c.atomic_write(lab_config, self.dns_config.read_text().replace(
            'server=127.0.0.1#5053', 'server=127.0.0.1#15953'), 0o644)
        argv = ['/usr/sbin/dnsmasq', '--conf-file=' + str(lab_config),
                '--port=15954', '--pid-file=' + str(Path(directory) / 'lab-dnsmasq.pid'),
                '--log-facility=-', '--cache-size=0', '--no-resolv',
                '--strip-subnet', '--strip-mac',
                '--add-subnet=32,128', '--add-mac']
        with open(Path(directory) / 'lab-dnsmasq.log', 'wb') as log:
            child = subprocess.Popen(argv, stdout=log, stderr=log, start_new_session=True)
            try:
                time.sleep(0.3)
                if child.poll() is not None:
                    raise c.Failure('The isolated LAN DNS listener could not start (exit ' + str(child.returncode) + ').')
                if options.ready_file:
                    c.atomic_write(Path(options.ready_file), 'ready')
                print('LAB READY: run probe-client.py --router ' + hosts[0] + ' --port 15954 on a LAN computer.', flush=True)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise c.Failure('The isolated LAN listener exited (exit ' + str(child.returncode) + ').')
                    proof = json.loads(proof_file.read_text())
                    if proof.get('query_sha256') != initial:
                        known = any(item['name'] == proof.get('device_name') and item['id'] == proof.get('device_id')
                                    for item in registry['by_ip'].values())
                        if not known:
                            raise c.Failure('Forwarded LAN device identity did not match the local registry.')
                        self.lan_proof = {'lan_forwarding': True, 'query_sha256': proof['query_sha256']}
                        return
                    time.sleep(0.1)
                raise c.Failure('No named LAN client probe arrived within thirty seconds.')
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready-file', help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.ready_file:
        Path(options.ready_file).unlink(missing_ok=True)
    controller = LANController(ROOT)
    try:
        with controller.lock():
            profile, _, _ = controller.preflight()
            result = controller.isolated_test(profile)
            result.update(controller.lan_proof)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
