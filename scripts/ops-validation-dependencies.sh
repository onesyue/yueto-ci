#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
uv venv --python "$YUE_CI_PYTHON" .venv
echo "${GITHUB_WORKSPACE}/.venv/bin" >> "$GITHUB_PATH"
requirements_file="${RUNNER_TEMP}/ci-requirements.txt"
uv export --frozen --no-default-groups \
  --group web-runtime --group checkin-runtime --group bot-runtime \
  --group image-build --group test \
  --no-emit-local --output-file "$requirements_file"
uv pip install --python .venv/bin/python \
  --require-hashes -r "$requirements_file"
uv pip install --python .venv/bin/python \
  --no-deps --no-build-isolation -e telegram-bot/yue \
  --config-settings editable_mode=compat
# Backend pytest contains fail-closed AST contracts that import the
# real locked TypeScript compiler. Install once before pytest; the
# later Mini App lint/build/audit reuses this exact clean tree.
# --ignore-scripts: no dependency install hook may execute inside the
# job that holds the source credential (npm supply-chain worms ride
# postinstall). The lockfile carries no build-time native deps; the
# only install script in it is macOS-only fsevents.
npm --prefix telegram-bot/yue/miniapp ci --ignore-scripts
