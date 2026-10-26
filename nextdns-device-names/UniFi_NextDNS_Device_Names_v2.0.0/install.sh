#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
chmod 755 "$PACKAGE_DIR/bin/dnscrypt-proxy"
exec python3 "$PACKAGE_DIR/v2.py" trial "$@"
