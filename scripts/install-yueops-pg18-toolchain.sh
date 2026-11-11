#!/usr/bin/env bash
# One runner installs PostgreSQL 18. Every yueops shard unpacks that archive
# and does not apt. apt-get update retries only DNS and transport failures:
# three attempts, then sleeps of 2s and 4s (ci_retry attempt * 2, jitter 1).
# A package miss, a bad signature, or a partial index is fatal immediately.
# Retrying those cannot make an unacceptable repository acceptable.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/ci-retry.sh
source "$here/ci-retry.sh"

pg_bin=/usr/lib/postgresql/18/bin

pack_toolchain() {
  local archive=$1 stage lib libs
  [ -n "$archive" ]
  [ -x "$pg_bin/postgres" ]
  stage=$(mktemp -d)
  mkdir -p "$stage$pg_bin"
  cp -a "$pg_bin/." "$stage$pg_bin/"
  if [ -d /usr/share/postgresql/18 ]; then
    mkdir -p "$stage/usr/share/postgresql"
    cp -a /usr/share/postgresql/18 "$stage/usr/share/postgresql/"
  fi
  if command -v ldd >/dev/null 2>&1; then
    libs=$(mktemp)
    if ldd "$pg_bin/postgres" "$pg_bin/initdb" "$pg_bin/pg_ctl" "$pg_bin/psql" >"$libs" 2>/dev/null; then
      while IFS= read -r lib; do
        [ -n "$lib" ] && [ -f "$lib" ] || continue
        mkdir -p "$stage$(dirname -- "$lib")"
        if [ ! -e "$stage$lib" ]; then
          cp -a "$lib" "$stage$lib"
        fi
      done < <(awk '/=> \// {print $3} /^\// {print $1}' "$libs")
    fi
    rm -f -- "$libs"
  fi
  tar -C "$stage" -cf "$archive" .
  rm -rf -- "$stage"
}

if [ "${1:-}" = pack ]; then
  pack_toolchain "${2:-}"
  exit 0
fi
if [ "$#" -ne 0 ]; then
  echo "usage: install-yueops-pg18-toolchain.sh [pack ARCHIVE]" >&2
  exit 2
fi

if [ ! -x "$pg_bin/postgres" ]; then
  elevate=(env)
  if [ "$(id -u)" -ne 0 ]; then
    elevate=(sudo -n)
  fi
  . /etc/os-release
  [ "${ID:-}" = ubuntu ]
  [ "${VERSION_ID:-}" = 24.04 ]
  [ "${VERSION_CODENAME:-}" = noble ]
  [ "$(dpkg --print-architecture)" = amd64 ]
  ubuntu_key=/usr/share/keyrings/ubuntu-archive-keyring.gpg
  [ -s "$ubuntu_key" ]
  [ -r "$ubuntu_key" ]
  # Use only reviewed Ubuntu and PGDG sources, including fresh list
  # state; unrelated runner repositories must not enter this install.
  apt_dir=$(mktemp -d /tmp/yueops-pg18-apt.XXXXXX)
  trap '"${elevate[@]}" rm -rf -- "$apt_dir"' EXIT
  chmod 0755 "$apt_dir"
  mkdir -m0755 "$apt_dir/sources.list.d" "$apt_dir/lists"
  printf '%s\n' \
    'Types: deb' 'URIs: https://archive.ubuntu.com/ubuntu' \
    'Suites: noble noble-updates' 'Components: main universe' \
    "Signed-By: $ubuntu_key" '' \
    'Types: deb' 'URIs: https://security.ubuntu.com/ubuntu' \
    'Suites: noble-security' 'Components: main universe' \
    "Signed-By: $ubuntu_key" > "$apt_dir/ubuntu.sources"
  apt=("${elevate[@]}" apt-get \
    -o "Dir::Etc::sourcelist=$apt_dir/ubuntu.sources" \
    -o "Dir::Etc::sourceparts=$apt_dir/sources.list.d" \
    -o "Dir::State::lists=$apt_dir/lists" \
    -o 'Dir::Cache::pkgcache=' -o 'Dir::Cache::srcpkgcache=' \
    -o APT::Update::Error-Mode=any \
    -o Acquire::AllowInsecureRepositories=false \
    -o Acquire::AllowDowngradeToInsecureRepositories=false \
    -o APT::Get::AllowUnauthenticated=false)
  ci_retry 3 2 1 "${apt[@]}" update
  "${apt[@]}" install -y --no-install-recommends ca-certificates curl gnupg
  pg_key="$apt_dir/pgdg.asc"
  curl --fail --silent --show-error --location \
    --retry 5 --retry-all-errors --retry-delay 2 \
    --proto '=https' --proto-redir '=https' --tlsv1.2 \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc --output "$pg_key"
  fingerprint=$(gpg --batch --show-keys --with-colons "$pg_key" | awk -F: '$1 == "fpr" && !seen {print $10; seen=1}')
  [ "$fingerprint" = B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8 ]
  chmod 0644 "$pg_key"
  printf '%s\n' \
    'Types: deb' 'URIs: https://apt.postgresql.org/pub/repos/apt' \
    "Suites: ${VERSION_CODENAME}-pgdg" 'Components: main' \
    "Signed-By: $pg_key" > "$apt_dir/sources.list.d/pgdg.sources"
  ci_retry 3 2 1 "${apt[@]}" update
  "${apt[@]}" install -y --no-install-recommends postgresql-18 postgresql-client-18
fi
for tool in postgres initdb pg_ctl psql; do
  [ -x "$pg_bin/$tool" ]
  "$pg_bin/$tool" --version | grep -E '\(PostgreSQL\) 18[.]'
done
# These fixtures use initdb as the runner user, never a production DB.
[ "$(id -u)" -ne 0 ] || { echo '::error::native PostgreSQL fixtures require a non-root runner'; exit 1; }
echo "$pg_bin" >> "$GITHUB_PATH"
