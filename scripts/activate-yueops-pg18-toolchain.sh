#!/usr/bin/env bash
# Shards reuse the archive from yueops-pg18-toolchain. This path never runs apt.
set -euo pipefail
archive=${1:?}
[ -f "$archive" ]
pg_bin=/usr/lib/postgresql/18/bin
elevate=(env)
if [ "$(id -u)" -ne 0 ]; then
  elevate=(sudo -n)
fi
"${elevate[@]}" tar -C / -xf "$archive"
for tool in postgres initdb pg_ctl psql; do
  [ -x "$pg_bin/$tool" ]
  "$pg_bin/$tool" --version | grep -E '\(PostgreSQL\) 18[.]'
done
# These fixtures use initdb as the runner user, never a production DB.
[ "$(id -u)" -ne 0 ] || { echo '::error::native PostgreSQL fixtures require a non-root runner'; exit 1; }
echo "$pg_bin" >> "$GITHUB_PATH"
