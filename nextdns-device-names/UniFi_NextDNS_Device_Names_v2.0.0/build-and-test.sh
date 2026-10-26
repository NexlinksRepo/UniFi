#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -m unittest discover -s "$PACKAGE_DIR/tests" -v
cd "$PACKAGE_DIR/source"
go test -mod=readonly ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -mod=readonly -trimpath -ldflags='-s -w' -o "$PACKAGE_DIR/bin/dnscrypt-proxy" ./dnscrypt-proxy
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go test -mod=readonly -c -ldflags='-s -w' -o "$PACKAGE_DIR/bin/proxy-tests-linux-arm64" ./dnscrypt-proxy
python3 "$PACKAGE_DIR/refresh-package.py"
