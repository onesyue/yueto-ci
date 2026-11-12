#!/bin/bash
# Proves the image can initdb, find sing-box 1.14, and compile against libpq without apt.
# Run as the non-root runner user: docker run --rm --user runner IMAGE yueops-ci-toolchain-selfcheck
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
  echo '::error::initdb fixtures require the non-root runner user' >&2
  exit 1
fi
test -e /usr/lib/postgresql/18/lib/plpgsql.so
test -e /usr/lib/postgresql/18/lib/dict_snowball.so
test -f "$(pg_config --includedir)/pg_config.h"
test -x /usr/bin/python3
/usr/bin/python3 -c 'import os, signal, sys; assert sys.version_info[:2] == (3, 13), sys.version; assert hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal")'
python3 -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version'
uv --version | grep -F '0.10.9'
go version | grep -F 'go1.27.4'
sing-box-1.14 version | grep -E '^sing-box version 1\.14\.'
nginx -v 2>&1 | grep -F 'nginx/1.30.5'
for tool in initdb pg_ctl psql gcc make node npm jq git buf docker corepack ssh-keygen rsync; do
  command -v "$tool" >/dev/null
done
data=$(mktemp -d)
trap 'pg_ctl -D "$data" stop >/dev/null 2>&1 || true; rm -rf -- "$data"' EXIT
initdb -D "$data" --username="$(id -un)" --auth=trust >/dev/null
pg_ctl -D "$data" -l "$data/log" -o "-k $data -c listen_addresses=" start
psql -h "$data" -d postgres -v ON_ERROR_STOP=1 -c 'SELECT 1'
echo 'ci-toolchain selfcheck ok'
