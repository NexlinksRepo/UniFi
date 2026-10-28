"""Refresh v3 release metadata and byte-exact source-patch checksums."""
import datetime
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def digest(data):return hashlib.sha256(data).hexdigest()
manifest=json.loads((ROOT/'manifest.json').read_text())
if not manifest.get('v3_created_utc'):
    manifest['previous_created_utc']=manifest['created_utc']
    manifest['v3_created_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest.update(package_version='3.0.1',previous_version='3.0.0',created_utc=manifest['v301_created_utc'],release_status='stable',
                updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),registry_version=2,
                candidate_sha256=digest((ROOT/'bin/dnscrypt-proxy').read_bytes()))
(ROOT/'manifest.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
records=json.loads((ROOT/'patches/source-hashes.json').read_text())
patch=[]
for name,record in records.items():
    old=ROOT/'patches/original'/name
    before=old.read_bytes() if old.exists() else None
    after=(ROOT/'source'/name).read_bytes()
    record.update(original=digest(before) if before is not None else None,patched=digest(after))
    patch.extend(difflib.unified_diff((before or b'').decode().splitlines(True),after.decode().splitlines(True),
                                    fromfile='a/'+name if before is not None else '/dev/null',tofile='b/'+name))
(ROOT/'patches/source-hashes.json').write_bytes((json.dumps(records,indent=2)+'\n').encode())
(ROOT/'patches/nextdns-device-names.patch').write_bytes(''.join(patch).encode())
for file,command in [('install.sh','trial'),('test.sh','test'),('status.sh','status'),('commit.sh','commit'),('rollback.sh','disable'),('disable.sh','disable'),('discover.sh','discover')]:
    text='#!/bin/sh\nset -eu\nPACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
    if command in ['trial','test']:text+='chmod 755 "$PACKAGE_DIR/bin/dnscrypt-proxy"\n'
    if command in ['commit','disable','status']:
        text+='if [ -f /data/nextdns-device-names-v3/v3.py ]; then\n    exec python3 /data/nextdns-device-names-v3/v3.py '+command+' "$@"\nfi\n'
    text+='exec python3 "$PACKAGE_DIR/v3.py" '+command+' "$@"\n'
    (ROOT/file).write_bytes(text.encode())
(ROOT/'update.sh').write_bytes(b'#!/bin/sh\nprintf "%s\\n" "Disable the current version, then install v3 with its five-minute trial. No in-place upgrade." >&2\nexit 1\n')
p=ROOT/'v3.py'
p.write_bytes(p.read_text().replace('integration v2','integration v3').encode())
(ROOT/'README.md').write_bytes((ROOT/'README-v3.md').read_bytes())
build='''#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PACKAGE_DIR/source"
go test -mod=readonly ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -mod=readonly -trimpath -ldflags='-s -w' -o "$PACKAGE_DIR/bin/dnscrypt-proxy" ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go test -mod=readonly -c -ldflags='-s -w' -o "$PACKAGE_DIR/bin/proxy-tests-linux-arm64" ./dnscrypt-proxy
python3 "$PACKAGE_DIR/refresh-package.py"
python3 -m unittest discover -s "$PACKAGE_DIR/tests" -v
'''
(ROOT/'build-and-test.sh').write_bytes(build.encode())
for script in ROOT.glob('*.sh'):script.write_bytes(script.read_bytes().replace(b'\r\n',b'\n'))
lines=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts and p.suffix!='.pyc':
        lines.append(digest(p.read_bytes())+'  '+p.relative_to(ROOT).as_posix())
(ROOT/'SHA256SUMS').write_bytes(('\n'.join(lines)+'\n').encode())
print('Refreshed v3 source metadata, entry points, and checksums')
