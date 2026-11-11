#!/usr/bin/env bash
# Prove one unpacked PostgreSQL 18 tree can initdb and load plpgsql.
# Uses the tools on PATH. Optional YUEOPS_PG18_SHARE and YUEOPS_PG18_LIB
# relocate the share directory and the extension directory.
# YUEOPS_PG18_ISOLATED=1 refuses LD_LIBRARY_PATH and does not set one.
set -euo pipefail
if [ "${YUEOPS_PG18_ISOLATED:-}" = 1 ] && [ -n "${LD_LIBRARY_PATH:-}" ]; then
  echo '::error::isolated PostgreSQL round trip refuses LD_LIBRARY_PATH' >&2
  exit 1
fi
for tool in initdb pg_ctl psql postgres; do
  command -v "$tool" >/dev/null 2>&1
done
data=$(mktemp -d "${TMPDIR:-/tmp}/yueops-pg18-roundtrip.XXXXXX")
cleanup() {
  pg_ctl -D "$data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf -- "$data"
}
trap cleanup EXIT
init_args=(--pgdata="$data" --username=yueops --auth=trust --no-sync --locale=C)
if [ -n "${YUEOPS_PG18_SHARE:-}" ]; then
  init_args+=(-L "$YUEOPS_PG18_SHARE")
fi
initdb "${init_args[@]}" >/dev/null
if [ -n "${YUEOPS_PG18_LIB:-}" ]; then
  printf "dynamic_library_path = '%s'\n" "$YUEOPS_PG18_LIB" >> "$data/postgresql.conf"
  if [ "${YUEOPS_PG18_ISOLATED:-}" != 1 ]; then
    export LD_LIBRARY_PATH="${YUEOPS_PG18_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
fi
pg_ctl -D "$data" -l "$data/server.log" -w -o "-k $data -c listen_addresses=" start >/dev/null
psql -h "$data" -U yueops -d postgres -v ON_ERROR_STOP=1 -c "DROP EXTENSION IF EXISTS plpgsql" >/dev/null
psql -h "$data" -U yueops -d postgres -v ON_ERROR_STOP=1 -c "CREATE EXTENSION plpgsql" >/dev/null
name=$(psql -h "$data" -U yueops -d postgres -v ON_ERROR_STOP=1 -At -c "SELECT extname FROM pg_extension WHERE extname = 'plpgsql'")
[ "$name" = plpgsql ]
printf '%s\n' plpgsql
