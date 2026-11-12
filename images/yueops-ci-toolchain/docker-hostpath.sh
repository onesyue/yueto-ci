#!/bin/bash
# The job container sees the runner work directory at /__w. The host Docker
# daemon, reached through the mounted socket, sees that same directory at
# /home/runner/work. Bind mounts written with the container path otherwise
# create an empty directory on the host.
set -euo pipefail
real=${DOCKER_REAL:-/usr/bin/docker}
args=()
prev=
for arg in "$@"; do
  current=$arg
  if [ "$prev" = "-v" ] || [ "$prev" = "--volume" ]; then
    src=${current%%:*}
    rest=${current#"$src"}
    src=${src//\/__w/\/home\/runner\/work}
    current=${src}${rest}
  elif [ "$prev" = "--mount" ]; then
    current=${current//source=\/__w/source=\/home\/runner\/work}
  fi
  args+=("$current")
  prev=$arg
done
exec "$real" "${args[@]}"
