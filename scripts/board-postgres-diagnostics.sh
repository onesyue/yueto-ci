#!/usr/bin/env bash
set -euo pipefail
# Configure the exact disposable service, independent of host port mapping.
[ -n "$PG_SERVICE" ]
pg() { docker exec "$PG_SERVICE" psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -Atqc "$1"; }
for setting in "log_lock_waits = on" "deadlock_timeout = '200ms'" \
  "log_line_prefix = '%m [%p] %q%u@%d app=%a xid=%x '"; do
  pg "ALTER SYSTEM SET $setting"
done
[ "$(pg 'SELECT pg_reload_conf()')" = t ]
# Reload is asynchronous; read all three settings from fresh sessions.
for _ in $(seq 1 20); do
  if [ "$(pg 'SHOW log_lock_waits')" = on ] && \
     [ "$(pg 'SHOW deadlock_timeout')" = 200ms ] && \
     [ "$(pg 'SHOW log_line_prefix')" = '%m [%p] %q%u@%d app=%a xid=%x ' ]; then
    exit 0
  fi
  sleep 0.5
done
echo '::error::PostgreSQL lock diagnostics did not take effect' >&2
exit 1
