#!/usr/bin/env python3
"""Test the real bind-mount restore and systemd recovery primitives in isolation.

Creates private temporary files and a uniquely named transient test service.
It never replaces a DNS binary, changes a DNS config or restarts native DNS.
"""
import json
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

if len(sys.argv) == 3 and sys.argv[1] == '--recovery-child':
    Path(sys.argv[2]).write_text('recovery-ran')
    raise SystemExit(0)

if len(sys.argv) == 4 and sys.argv[1] == '--handoff-child':
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('controller', root / 'controller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = Path(sys.argv[2])
    controller = module.Controller(root, runtime=folder)
    def private_recovery(state, reason):
        (folder / 'forced-recovery').write_text('recovered')
        return {'restored': True}
    controller.rollback_locked = private_recovery
    result = controller.recover(force=sys.argv[3] == 'force')
    (folder / 'handoff-dispatch').write_text(json.dumps(result))
    raise SystemExit(0)

if sys.platform != 'linux' or os.geteuid() != 0:
    raise SystemExit('Run this optional runtime drill as root on the gateway.')


def run(args, check=True):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=20, check=check)


unit_name = 'ndn-runtime-drill-' + secrets.token_hex(6) + '.service'
unit_path = Path('/run/systemd/system') / unit_name
guard_name = unit_name.removesuffix('.service') + '-guard'
mounted = False
executable = None
with tempfile.TemporaryDirectory(prefix='ndn-runtime-drill-', dir='/tmp') as folder:
    folder = Path(folder)
    source, target, proof = folder / 'candidate', folder / 'stock', folder / 'recovery-proof'
    # An idle file mount does not reproduce the failure of a running ELF file.
    shutil.copy2('/usr/bin/sleep', source)
    target.write_text('stock')
    target.chmod(0o755)
    try:
        run(['mount', '--bind', str(source), str(target)])
        mounted = True
        if target.read_bytes() != source.read_bytes():
            raise RuntimeError('The test mount did not take effect.')
        executable = subprocess.Popen([str(target), '60'])
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('controller', root / 'controller.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        controller = module.Controller(root)
        controller.native = target
        controller.manifest['candidate_sha256'] = module.digest(source)
        controller.detach_proxy()
        mounted = False
        if target.read_text() != 'stock':
            raise RuntimeError('The original test file did not return after unmount.')
        unit_path.write_text('[Unit]\nDescription=Isolated NextDNS recovery drill\n'
                             '[Service]\nType=simple\n'
                             'ExecStart=/usr/bin/python3 -c "import time; time.sleep(60)"\n'
                             'ExecStopPost=/usr/bin/python3 ' + str(Path(__file__).resolve())
                             + ' --recovery-child ' + str(proof) + '\nTimeoutStopSec=15\n')
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', unit_name])
        run(['systemctl', 'kill', '--signal=SIGKILL', unit_name])
        deadline = time.monotonic() + 10
        while not proof.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not proof.exists() or proof.read_text() != 'recovery-ran':
            raise RuntimeError('systemd did not run recovery after the test process was killed.')
        unit_path.write_text('[Unit]\nDescription=Isolated monitor handoff drill\n'
                             '[Service]\nType=simple\n'
                             'ExecStart=/usr/bin/python3 -c "import time; time.sleep(60)"\n'
                             'ExecStopPost=/usr/bin/python3 ' + str(Path(__file__).resolve())
                             + ' --handoff-child ' + str(folder) + ' normal\nTimeoutStopSec=15\n')
        module.atomic_write(folder / 'monitor-handoff.json', json.dumps({
            'boot_id': controller.boot_id(), 'expires_unix': int(time.time()) + 30,
            'candidate_sha256': module.Controller(root).manifest['candidate_sha256']}))
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'reset-failed', unit_name], check=False)
        run(['systemctl', 'start', unit_name])
        run(['systemctl', 'kill', '--signal=SIGKILL', unit_name])
        deadline = time.monotonic() + 8
        dispatch = folder / 'handoff-dispatch'
        while not dispatch.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not dispatch.exists() or not json.loads(dispatch.read_text()).get('recovery_deferred'):
            raise RuntimeError('The private handoff did not defer ExecStopPost recovery.')
        if (folder / 'forced-recovery').exists():
            raise RuntimeError('A valid handoff unexpectedly performed recovery.')
        run(['systemd-run', '--quiet', '--unit=' + guard_name, '--on-active=2s',
             '--timer-property=AccuracySec=1s', '/usr/bin/python3', str(Path(__file__).resolve()),
             '--handoff-child', str(folder), 'force'])
        deadline = time.monotonic() + 8
        while not (folder / 'forced-recovery').exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not (folder / 'forced-recovery').exists():
            raise RuntimeError('The independent timer did not override the handoff and recover.')
        print(json.dumps({'running_executable_mount_restore': True,
                          'systemd_recovery_after_sigkill': True,
                          'handoff_execstoppost_deferred': True,
                          'independent_timer_forced_recovery': True}))
    finally:
        run(['systemctl', 'stop', unit_name], check=False)
        run(['systemctl', 'reset-failed', unit_name], check=False)
        run(['systemctl', 'stop', guard_name + '.timer', guard_name + '.service'], check=False)
        run(['systemctl', 'reset-failed', guard_name + '.service'], check=False)
        if unit_path.exists():
            unit_path.unlink()
        run(['systemctl', 'daemon-reload'])
        if executable is not None and executable.poll() is None:
            executable.terminate()
            executable.wait(timeout=3)
        if mounted:
            run(['umount', str(target)])
