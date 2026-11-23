#!/bin/bash
# The job container sees the runner work directory at /__w. The host Docker
# daemon, reached through the mounted socket, sees that same directory at
# /home/runner/work. Bind mounts written with the container path otherwise
# create an empty directory on the host.
set -euo pipefail
real=${DOCKER_REAL:-/usr/bin/docker}
# Docker parses --mount as CSV. A quoted field can contain commas and quotes.
mount_source='^((([^",]*|"([^"]|"")*"),)*"?(source|src)=)/__w([/",]|$)'
args=()
prev=
for arg in "$@"; do
  current=$arg
  if [ "$prev" = "-v" ] || [ "$prev" = "--volume" ]; then
    case "$current" in
      /__w:*|/__w/*:*) current=/home/runner/work${current#/__w} ;;
    esac
  elif [ "$prev" = "--mount" ] && [[ $current =~ $mount_source ]]; then
    prefix=${BASH_REMATCH[1]}
    current=${prefix}/home/runner/work${current#"${prefix}/__w"}
  fi
  args+=("$current")
  prev=$arg
done
exec "$real" "${args[@]}"
