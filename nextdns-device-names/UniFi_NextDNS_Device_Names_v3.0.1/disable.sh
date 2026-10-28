#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f /data/nextdns-device-names-v3/v3.py ]; then
    exec python3 /data/nextdns-device-names-v3/v3.py disable "$@"
fi
exec python3 "$PACKAGE_DIR/v3.py" disable "$@"
