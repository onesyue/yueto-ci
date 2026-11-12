#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
npm --prefix telegram-bot/yue/miniapp test
npm --prefix frontend test
corepack enable
site_pm=$(node -p "require('./site/package.json').packageManager || ''")
[ -n "$site_pm" ] || {
  echo "::error::site/package.json has no packageManager pin"
  exit 1
}
corepack install --global "$site_pm"
pnpm --dir site install --frozen-lockfile --ignore-scripts
deps=()
if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then deps=(--with-deps); fi
pnpm --dir site exec playwright install "${deps[@]}" chromium
pnpm --dir site test
