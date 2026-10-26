#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f /data/nextdns-device-names-v2/v2.py ]; then
    exec python3 /data/nextdns-device-names-v2/v2.py commit "$@"
fi
exec python3 "$PACKAGE_DIR/v2.py" commit "$@"
