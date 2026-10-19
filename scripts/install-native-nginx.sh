#!/usr/bin/env bash
# Install the reviewed native-test toolchain on disposable Ubuntu runners only.
# --package-cache is offline for NGINX itself; apt still resolves OS dependencies.
set -euo pipefail

fail() { printf 'native-nginx: %s\n' "$*" >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
package_cache=
if [[ $# == 2 && $1 == --package-cache ]]; then
  package_cache=$2
elif [[ $# != 0 ]]; then
  fail 'usage: install-native-nginx.sh [--package-cache DIRECTORY]'
fi
[[ $(uname -s) == Linux && $(id -u) == 0 ]] || fail 'requires disposable Linux UID0'
for tool in python3 dpkg dpkg-deb dpkg-query apt-get; do
  command -v "$tool" >/dev/null || fail "missing $tool"
done
architecture=$(dpkg --print-architecture)
. /etc/os-release
distribution=${ID:-}
codename=${VERSION_CODENAME:-}
# Read one canonical input manifest. Unsupported platforms fail before apt/curl.
inputs=$(python3 -I - "$script_dir/native-nginx-toolchain.json" "$architecture" "$distribution" "$codename" <<'PY'
import json, re, sys
from urllib.parse import urlsplit
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
assert manifest['schema'] == 1
assert (sys.argv[3], sys.argv[4]) == (manifest['distribution'], manifest['codename']), 'unsupported distribution'
assert sys.argv[2] in ('amd64', 'arm64'), 'unsupported architecture'
assert set(manifest['packages']) == {'amd64', 'arm64'}
package = manifest['packages'][sys.argv[2]]
assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', manifest['version'])
assert manifest['package_version'] == manifest['version'] + '-1~noble'
filename = 'nginx_' + manifest['package_version'] + '_' + sys.argv[2] + '.deb'
url = urlsplit(package['url'])
assert url.scheme == 'https' and url.netloc == 'nginx.org' and not url.query and not url.fragment
assert url.path == '/packages/ubuntu/pool/nginx/n/nginx/' + filename
assert re.fullmatch(r'[a-f0-9]{64}', package['sha256'])
print('\n'.join([manifest['version'], manifest['package_version'], package['url'], package['sha256'], filename]))
PY
)
mapfile -t fields <<< "$inputs"
[[ ${#fields[@]} == 5 ]] || fail 'incomplete manifest inputs'
version=${fields[0]}
package_version=${fields[1]}
url=${fields[2]}
expected_sha=${fields[3]}
filename=${fields[4]}
work=$(mktemp -d)
policy=/usr/sbin/policy-rc.d
policy_changed=0
policy_saved=0
cleanup() {
  local result=$?
  trap - EXIT
  if [[ $policy_changed == 1 ]]; then
    if [[ $policy_saved == 1 ]]; then
      cp -p -- "$work/policy-rc.d.original" "$policy" || result=1
    else
      rm -f -- "$policy" || result=1
    fi
  fi
  rm -rf -- "$work"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ -n $package_cache ]]; then
  [[ -f $package_cache/$filename ]] || fail 'offline package missing'
  # Freeze the supplied bytes before validation and the later apt transaction.
  cp -- "$package_cache/$filename" "$work/$filename"
else
  command -v curl >/dev/null || fail 'missing curl'
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 120 "$url" --output "$work/$filename"
fi
package=$work/$filename
python3 -I - "$package" "$expected_sha" <<'PY'
import hashlib, pathlib, sys
assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() == sys.argv[2], 'package SHA256 mismatch'
PY
[[ $(dpkg-deb -f "$package" Package) == nginx ]] || fail 'unexpected package name'
[[ $(dpkg-deb -f "$package" Version) == "$package_version" ]] || fail 'unexpected package version'
[[ $(dpkg-deb -f "$package" Architecture) == "$architecture" ]] || fail 'unexpected package architecture'

# Prevent maintainer scripts from starting a listener; restore the exact policy.
[[ ! -L $policy ]] || fail 'refuse a symlinked service policy'
if [[ -e $policy ]]; then
  [[ -f $policy ]] || fail 'service policy is not a regular file'
  cp -p -- "$policy" "$work/policy-rc.d.original"
  policy_saved=1
fi
printf '#!/bin/sh\nexit 101\n' > "$work/policy-rc.d"
policy_changed=1
install -m 0755 "$work/policy-rc.d" "$policy"
export DEBIAN_FRONTEND=noninteractive
apt-get update
if [[ $(dpkg-query -W -f='${Status}' libnginx-mod-stream 2>/dev/null || true) == 'install ok installed' ]]; then
  apt-get remove -y libnginx-mod-stream
fi
apt-get install -y --no-install-recommends --allow-downgrades "$package" logrotate
[[ $(dpkg-query -W -f='${Version}' nginx) == "$package_version" ]] || fail 'installed package version differs'
[[ $(command -v nginx) == /usr/sbin/nginx ]] || fail 'PATH selects an unexpected nginx binary'
[[ $(nginx -v 2>&1) == "nginx version: nginx/$version" ]] || fail 'executed nginx version differs'
configuration=$(nginx -V 2>&1)
for flag in --with-stream --with-stream_ssl_module --with-stream_ssl_preread_module --with-http_ssl_module; do
  [[ " $configuration " == *" $flag "* ]] || fail "missing native capability $flag"
done
cat > "$work/nginx.conf" <<EOF
pid $work/nginx.pid;
error_log stderr;
events {}
http {
    access_log off;
    keepalive_min_timeout 5s;
    client_body_temp_path $work/client_temp;
    proxy_temp_path $work/proxy_temp;
    fastcgi_temp_path $work/fastcgi_temp;
    uwsgi_temp_path $work/uwsgi_temp;
    scgi_temp_path $work/scgi_temp;
}
stream {}
EOF
nginx -t -p "$work/" -c "$work/nginx.conf"
printf 'NATIVE_NGINX_TOOLCHAIN_READY version=%s package=%s architecture=%s binary=/usr/sbin/nginx stream=static\n' \
  "$version" "$package_version" "$architecture"
