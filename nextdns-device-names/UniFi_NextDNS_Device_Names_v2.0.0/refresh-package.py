"""Refresh source patch metadata, v2 entry points, and package checksums."""
import difflib
import hashlib
import json
import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if not (ROOT/'manifest.json').exists():
    ROOT=ROOT/'v2-work/UniFi_NextDNS_Device_Names_v2.0.0'
def digest(data):return hashlib.sha256(data).hexdigest()

manifest=json.loads((ROOT/'manifest.json').read_text())
if 'v1_origin_created_utc' not in manifest:
    manifest['v1_origin_created_utc']=manifest['created_utc']
    manifest['created_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest.update(package_version='2.0.0',integration='external-systemd-reconciler',native_unifi_integration=False,
                go_version='go1.27.3',registry_version=2)
manifest['candidate_sha256']=digest((ROOT/'bin/dnscrypt-proxy').read_bytes())
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
records=json.loads((ROOT/'patches/source-hashes.json').read_text())
records['dnscrypt-proxy/nextdns_v2_test.go']={'original':None,'patched':None}
patch=[]
for name, record in records.items():
    old=ROOT/'patches/original'/name
    before=old.read_bytes() if old.exists() else None
    after=(ROOT/'source'/name).read_bytes()
    record.update(original=digest(before) if before is not None else None,patched=digest(after))
    patch.extend(difflib.unified_diff((before or b'').decode().splitlines(True),after.decode().splitlines(True),
                                    fromfile='a/'+name if before is not None else '/dev/null',tofile='b/'+name))
(ROOT/'patches/source-hashes.json').write_text(json.dumps(records,indent=2)+'\n')
(ROOT/'patches/nextdns-device-names.patch').write_text(''.join(patch))
for file,command in [('install.sh','trial'),('test.sh','test'),('status.sh','status'),('commit.sh','commit'),('rollback.sh','disable'),('disable.sh','disable'),('discover.sh','discover')]:
    text='#!/bin/sh\nset -eu\nPACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
    if command in ['trial','test']:
        text+='chmod 755 "$PACKAGE_DIR/bin/dnscrypt-proxy"\n'
    if command in ['commit','disable','status']:
        text+='if [ -f /data/nextdns-device-names-v2/v2.py ]; then\n    exec python3 /data/nextdns-device-names-v2/v2.py '+command+' "$@"\nfi\n'
    text+='exec python3 "$PACKAGE_DIR/v2.py" '+command+' "$@"\n'
    (ROOT/file).write_text(text)
(ROOT/'update.sh').write_text('#!/bin/sh\nprintf "%s\\n" "No in-place v1/v2 upgrade: disable the existing version, then use install.sh." >&2\nexit 1\n')
(ROOT/'README.md').write_bytes((ROOT/'README-v2.md').read_bytes())
if (ROOT/'TEST-RESULTS.md').exists() and not (ROOT/'V1-TEST-RESULTS.md').exists():
    (ROOT/'V1-TEST-RESULTS.md').write_bytes((ROOT/'TEST-RESULTS.md').read_bytes())
(ROOT/'refresh-package.py').write_bytes(Path(__file__).read_bytes())
(ROOT/'build-and-test.sh').write_text('''#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -m unittest discover -s "$PACKAGE_DIR/tests" -v
cd "$PACKAGE_DIR/source"
go test -mod=readonly ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -mod=readonly -trimpath -ldflags='-s -w' -o "$PACKAGE_DIR/bin/dnscrypt-proxy" ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go test -mod=readonly -c -ldflags='-s -w' -o "$PACKAGE_DIR/bin/proxy-tests-linux-arm64" ./dnscrypt-proxy
python3 "$PACKAGE_DIR/refresh-package.py"
''')
for script in ROOT.glob('*.sh'):
    script.write_bytes(script.read_bytes().replace(b'\r\n',b'\n'))
lines=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts and p.suffix!='.pyc':
        lines.append(digest(p.read_bytes())+'  '+p.relative_to(ROOT).as_posix())
(ROOT/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
print('Updated v2 entry points, manifest, source patch, and checksums')
