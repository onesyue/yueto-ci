#!/usr/bin/env bash
# Native tests put PATH-first doubles under /run. Python's execvpe keeps
# searching after EACCES, so a noexec mount runs the real docker or systemctl.
# This prepares the disposable runner mount and refuses to continue when a
# non-executable first hit is treated as success, or when a real double is not.
set -euo pipefail

fail() { printf 'native-run-exec: %s\n' "$*" >&2; exit 1; }

probe_directory() {
  local root=$1 py bin later name
  [[ -d $root && ! -L $root ]] || fail "probe root is not a directory: $root"
  py=$(command -v python3) || fail 'python3 missing'
  py=$("$py" -c 'import sys; print(sys.executable)')
  [[ -x $py ]] || fail "python interpreter is not executable: $py"
  bin=$root/bin
  later=$root/later
  mkdir -m 0755 "$bin" "$later"
  cat > "$root/check.py" <<'PY'
import subprocess
import sys

name = sys.argv[1]
result = subprocess.run([name, "probe"], capture_output=True, text=True)
ok = result.returncode == 0 and result.stdout == "YUE_NATIVE_EXEC_PROBE\n"
if not ok:
    sys.stderr.write(result.stdout + result.stderr)
    raise SystemExit(1)
PY
  write_double() {
    local name=$1 mode=$2
    if [[ $name == docker ]]; then
      printf '#!%s\nimport sys\nprint("YUE_NATIVE_EXEC_PROBE")\nraise SystemExit(0 if sys.argv[1:] == ["probe"] else 1)\n' "$py" > "$bin/$name"
    else
      cat > "$bin/$name" <<'EOF'
#!/bin/bash
[[ $1 == probe ]] || exit 1
printf 'YUE_NATIVE_EXEC_PROBE\n'
EOF
    fi
    cat > "$later/$name" <<'EOF'
#!/bin/bash
printf 'YUE_NATIVE_EXEC_REAL\n'
exit 1
EOF
    chmod "$mode" "$bin/$name"
    chmod 0755 "$later/$name"
  }
  check_name() {
    local name=$1
    PATH="$bin:$later:/usr/bin:/bin" "$py" -I -B "$root/check.py" "$name"
  }
  for name in docker systemctl; do
    write_double "$name" 0644
    if check_name "$name"; then
      fail "non-executable PATH-first $name was accepted"
    fi
    chmod 0755 "$bin/$name"
    if ! check_name "$name"; then
      printf 'native-run-exec: PATH-first %s double was not executed\n' "$name" >&2
      return 1
    fi
  done
}

if [[ ${1:-} == --probe-only ]]; then
  [[ $# == 2 && -n $2 ]] || fail 'usage: prepare-native-run-exec.sh --probe-only DIRECTORY'
  probe_directory "$2"
  exit 0
fi
[[ $# == 0 ]] || fail 'usage: prepare-native-run-exec.sh [--probe-only DIRECTORY]'
[[ $(uname -s) == Linux ]] || fail 'requires Linux'
[[ $(id -u) == 0 ]] || fail 'requires UID0'
command -v findmnt >/dev/null || fail 'missing findmnt'
command -v mount >/dev/null || fail 'missing mount'

target=$(findmnt -n -o TARGET --target /run)
options=$(findmnt -n -o OPTIONS --target /run)
[[ -n $target && -n $options ]] || fail 'cannot read the /run mount'
printf 'native-run-exec: mount=%s options=%s\n' "$target" "$options"
case ",$options," in
  *,noexec,*)
    [[ $target == /run ]] || fail "refusing to remount $target; /run is not its own mount"
    mount -o remount,exec /run || fail 'remount exec failed for /run'
    options=$(findmnt -n -o OPTIONS --target /run)
    printf 'native-run-exec: remounted options=%s\n' "$options"
    ;;
esac
case ",$options," in
  *,noexec,*) fail '/run remains noexec' ;;
esac

probe=$(mktemp -d /run/yue-native-exec-probe.XXXXXX)
trap 'rm -rf -- "$probe"' EXIT
chmod 0755 "$probe"
if ! probe_directory "$probe"; then
  printf 'native-run-exec: probe failed\n' >&2
  findmnt -T /run >&2 || true
  if command -v aa-status >/dev/null 2>&1; then
    aa-status >&2 || true
  fi
  exit 1
fi
printf 'native-run-exec: PATH-first doubles under /run execute\n'
