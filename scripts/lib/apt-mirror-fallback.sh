#!/usr/bin/env bash
# Sourced immediately before Playwright's privileged `install --with-deps`.
# No-op unless this process is root or has passwordless sudo. When
# archive.ubuntu.com does not answer, rewrite only those Ubuntu archive hosts
# (and security.ubuntu.com) to azure.archive.ubuntu.com, then apt-get update.
# Other repositories, schemes, and an already-working probe stay untouched.
#
# Tests can point this at a fake curl and a temporary sources tree:
#   YUETO_APT_CURL, YUETO_APT_GET, YUETO_APT_OS_RELEASE, YUETO_APT_SOURCES_DIR

yueto_apt_run() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo -n "$@"
  fi
}

yueto_apt_mirror_fallback() {
  local sources_dir os_release curl_bin apt_get codename probe_url changed file tmp
  sources_dir=${YUETO_APT_SOURCES_DIR:-/etc/apt}
  os_release=${YUETO_APT_OS_RELEASE:-/etc/os-release}
  curl_bin=${YUETO_APT_CURL:-curl}
  apt_get=${YUETO_APT_GET:-apt-get}
  changed=0

  if [ "$(id -u)" -eq 0 ]; then
    :
  elif ! sudo -n true 2>/dev/null; then
    return 0
  fi

  if [ ! -f "$os_release" ]; then
    echo "apt-mirror-fallback: OS release file is missing" >&2
    return 1
  fi
  # shellcheck disable=SC1090
  codename=$(
    # shellcheck disable=SC1090
    . "$os_release"
    printf '%s' "${VERSION_CODENAME:-}"
  )
  case $codename in
    ""|*[!a-z0-9]*|[0-9]*)
      echo "apt-mirror-fallback: unsupported VERSION_CODENAME" >&2
      return 1
      ;;
  esac
  probe_url="http://archive.ubuntu.com/ubuntu/dists/${codename}/InRelease"
  if "$curl_bin" -fsS --max-time 10 -o /dev/null "$probe_url"; then
    return 0
  fi

  if [ ! -d "$sources_dir" ] || [ -L "$sources_dir" ]; then
    echo "apt-mirror-fallback: apt sources directory is missing" >&2
    return 1
  fi

  for file in \
    "$sources_dir/sources.list" \
    "$sources_dir/sources.list.d/"*.list \
    "$sources_dir/sources.list.d/"*.sources
  do
    [ -f "$file" ] || continue
    # A symlink can point at a non-Ubuntu file outside this directory.
    [ -L "$file" ] && continue
    tmp=$(mktemp "${TMPDIR:-/tmp}/apt-mirror-fallback.XXXXXX") || return 1
    sed -E \
      -e 's#(^|[^A-Za-z0-9.-])archive\.ubuntu\.com([^A-Za-z0-9.-]|$)#\1azure.archive.ubuntu.com\2#g' \
      -e 's#(^|[^A-Za-z0-9.-])security\.ubuntu\.com([^A-Za-z0-9.-]|$)#\1azure.archive.ubuntu.com\2#g' \
      "$file" > "$tmp" || { rm -f -- "$tmp"; return 1; }
    if cmp -s "$file" "$tmp"; then
      rm -f -- "$tmp"
      continue
    fi
    if ! yueto_apt_run tee "$file" < "$tmp" >/dev/null; then
      rm -f -- "$tmp"
      return 1
    fi
    rm -f -- "$tmp"
    changed=1
  done

  if [ "$changed" -eq 1 ]; then
    echo "::notice::Ubuntu archive mirror unreachable; apt sources now use azure.archive.ubuntu.com"
  fi
  yueto_apt_run "$apt_get" -o Acquire::Retries=3 -o Acquire::http::Timeout=20 update
}

yueto_apt_mirror_fallback
