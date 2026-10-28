#!/usr/bin/env python3
"""Apply or reverse the audited source changes in a matching upstream checkout.

The included source/ directory is already patched. This script is only needed
when applying the patch to a fresh dnscrypt-proxy 2.1.14 source checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(source, reverse=False):
    source = Path(source).resolve()
    records = json.loads((ROOT / 'patches/source-hashes.json').read_text())
    plans = []
    for relative, hashes in records.items():
        destination = source / relative
        if destination.is_symlink() or not destination.resolve().is_relative_to(source):
            raise RuntimeError('Unsafe source path: ' + relative)
        current = destination.read_bytes() if destination.exists() else None
        old_hash = sha(current) if current is not None else None
        expected = hashes['patched'] if reverse else hashes['original']
        desired = hashes['original'] if reverse else hashes['patched']
        if old_hash == desired:
            continue  # The requested state is already present.
        if old_hash != expected:
            raise RuntimeError('Source version/hash mismatch: ' + relative)
        data = ((ROOT / 'patches/original' / relative).read_bytes() if reverse else
                (ROOT / 'source' / relative).read_bytes()) if desired else None
        if data is not None and sha(data) != desired:
            raise RuntimeError('Patch payload checksum mismatch: ' + relative)
        plans.append((destination, current, data))
    changed = []
    try:
        for destination, current, data in plans:
            changed.append((destination, current))
            if data is None:
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
    except BaseException:
        for destination, previous in reversed(changed):
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                destination.write_bytes(previous)
        raise
    return len(plans)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Path to an upstream dnscrypt-proxy checkout')
    parser.add_argument('--reverse', action='store_true')
    options = parser.parse_args()
    try:
        print(json.dumps({'changed_files': apply(options.source, options.reverse), 'reversed': options.reverse}))
    except (OSError, ValueError, RuntimeError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
