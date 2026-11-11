#!/usr/bin/env bash
# Shards reuse the archive from yueops-pg18-toolchain. This path never runs apt.
# Bytes stay under RUNNER_TEMP. Compiled paths are symlinks to that tree, so
# initdb and $libdir/plpgsql resolve. libc and the dynamic loader are not extracted.
set -euo pipefail
archive=${1:?}
[ -f "$archive" ]
runner_temp=${RUNNER_TEMP:?}
dest=$runner_temp/yueops-pg18
rm -rf -- "$dest"
mkdir -p "$dest"
tar -C "$dest" -xf "$archive"
if find "$dest" \( -name 'libc.so*' -o -name 'ld-linux*' \) -print | grep -q .; then
  echo '::error::toolchain archive carries libc or the dynamic loader' >&2
  exit 1
fi
pg_prefix=$dest/usr/lib/postgresql/18
pg_share=$dest/usr/share/postgresql/18
[ -x "$pg_prefix/bin/postgres" ]
[ -e "$pg_prefix/lib/plpgsql.so" ]
[ -e "$pg_prefix/lib/dict_snowball.so" ]
[ -f "$pg_share/postgres.bki" ]
sysroot=${YUEOPS_PG18_SYSROOT:-}
link_lib=$sysroot/usr/lib/postgresql/18
link_share=$sysroot/usr/share/postgresql/18
elevate=(env)
if [ "$(id -u)" -ne 0 ] && [ -z "$sysroot" ]; then
  elevate=(sudo -n)
fi
"${elevate[@]}" mkdir -p -- "$(dirname -- "$link_lib")" "$(dirname -- "$link_share")"
if [ -e "$link_lib" ] || [ -L "$link_lib" ]; then
  echo '::error::refusing to replace an existing PostgreSQL 18 prefix' >&2
  exit 1
fi
if [ -e "$link_share" ] || [ -L "$link_share" ]; then
  echo '::error::refusing to replace an existing PostgreSQL 18 share' >&2
  exit 1
fi
"${elevate[@]}" ln -s -- "$pg_prefix" "$link_lib"
"${elevate[@]}" ln -s -- "$pg_share" "$link_share"
pg_bin=$link_lib/bin
for tool in postgres initdb pg_ctl psql; do
  [ -x "$pg_bin/$tool" ]
  "$pg_bin/$tool" --version | grep -E '\(PostgreSQL\) 18[.]'
done
[ "$(id -u)" -ne 0 ] || { echo '::error::native PostgreSQL fixtures require a non-root runner'; exit 1; }
echo "$pg_bin" >> "${GITHUB_PATH:?}"
printf 'LD_LIBRARY_PATH=%s\n' "$pg_prefix/lib" >> "${GITHUB_ENV:?}"
