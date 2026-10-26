#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$PACKAGE_DIR/v3.py" discover "$@"
