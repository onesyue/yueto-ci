#!/bin/bash
# Seed the Docker lab images that ordinary yueops tests run by tag
# (nginx:1.28-alpine, python:3.13-alpine). Without this, `docker run` pulled
# them anonymously from Docker Hub and the shared runner IP hit its pull
# limit (yueops official 46172687868, 2026-11-29: toomanyrequests in
# test_panel_spa_error_cache_e2e). Digest-pinned, so the bytes are identical
# from any registry; mirror.gcr.io (Google's Docker Hub mirror) first, Docker
# Hub as the fallback. The pull verifies the digest.
set -euo pipefail
if ! command -v docker >/dev/null 2>&1; then
  echo "ops lab images: docker absent; docker-backed tests skip"
  exit 0
fi
while read -r tag digest; do
  name=${tag%%:*}
  seeded=
  for repo in "mirror.gcr.io/library/$name" "docker.io/library/$name"; do
    if docker pull --quiet "$repo@$digest"; then
      seeded="$repo@$digest"
      break
    fi
  done
  if [ -z "$seeded" ]; then
    echo "ops lab images: cannot pull $tag@$digest from any registry" >&2
    exit 1
  fi
  docker tag "$seeded" "$tag"
  test "$(docker image inspect --format '{{.Id}}' "$seeded")" = \
    "$(docker image inspect --format '{{.Id}}' "$tag")"
done <<'IMAGES'
nginx:1.28-alpine sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
python:3.13-alpine sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e
IMAGES
