#!/usr/bin/env bash
# Sourced by owned role containers; never addresses the host daemon.
ci_check_daemon_start() {
  # shellcheck disable=SC2024
  sudo dockerd --host unix:///var/run/docker.sock --group runner \
    --data-root /var/lib/ci-check-docker --exec-root /run/ci-check-docker \
    --pidfile /run/ci-check-docker.pid --storage-driver vfs \
    > "$RUNNER_TEMP/docker-daemon.log" 2>&1 &
  daemon_pid=$!
  local ready=false attempt
  for ((attempt = 0; attempt < 60; attempt++)); do
    if timeout 3 docker info >/dev/null 2>&1; then ready=true; break; fi
    kill -0 "$daemon_pid" 2>/dev/null || break
    sleep 1
  done
  [ "$ready" = true ] || { cat "$RUNNER_TEMP/docker-daemon.log" >&2; return 1; }
}
ci_check_daemon_stop() {
  if [ -n "${daemon_pid:-}" ]; then
    sudo kill -TERM "$daemon_pid" 2>/dev/null || true
    wait "$daemon_pid" 2>/dev/null || true
  fi
}
