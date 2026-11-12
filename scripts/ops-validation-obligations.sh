#!/bin/bash
# Shared by build.yml and ci-check --local; run from the source checkout.
set -euo pipefail
export YUEBOARD_MONEY_SCHEMA_FIXTURE=${YUEBOARD_MONEY_SCHEMA_FIXTURE:-$PWD/.ci-yueboard/test/fixtures/schema.sql}
# Use the reviewed checkout, not an unbound local schema or moving ref.
board_pin=$(jq -er '.yueboard_contract_pin | select(test("^[0-9a-f]{40}$"))' .ci-policy/native-node-contract.json)
test "$(git -C .ci-yueboard rev-parse HEAD)" = "$board_pin"
test -f "$YUEBOARD_MONEY_SCHEMA_FIXTURE"
test ! -L "$YUEBOARD_MONEY_SCHEMA_FIXTURE"
git -C .ci-yueboard diff --exit-code "$board_pin" -- test/fixtures/schema.sql
test "$(id -u)" = 1001
native_evidence="${RUNNER_TEMP:?}/ops-shard-evidence"
.venv/bin/python .ci-policy/scripts/pytest-shards.py native-start \
  --admission "$RUNNER_TEMP/ops-admission/ops-admission.json" \
  --source "$PWD" --board "$PWD/.ci-yueboard" --output "$native_evidence"
native_driver=$(mktemp "${RUNNER_TEMP:?}/yueops-native.XXXXXX.py")
trap 'rm -f -- "$native_driver"' EXIT
cat > "$native_driver" <<'PY'
import importlib.util
import json
import os
from pathlib import Path
import sys

target, floor, uid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
if sys.platform != "linux" or os.geteuid() != uid:
    raise SystemExit("native obligation execution context differs")
import pytest
source = Path.cwd() / "scripts/run-native-nginx-tests.py"
spec = importlib.util.spec_from_file_location("source_native_gate", source)
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)

class RequiredCases(consumer.NativeGate):
    def __init__(self):
        super().__init__([])
        self.collection_bad = False

    def pytest_deselected(self, items):
        self.collection_bad = True

    def pytest_collectreport(self, report):
        if report.failed or report.skipped:
            self.collection_bad = True

    def pytest_collection_finish(self, session):
        names = [item.nodeid for item in session.items]
        self.required = set(names)
        self.collection_bad |= (
            len(names) != len(self.required) or len(names) < floor
            or any(not name.startswith(target + "::") for name in names)
        )

    def pytest_sessionfinish(self, session, exitstatus):
        super().pytest_sessionfinish(session, exitstatus)
        if self.collection_bad or len(self.required) < floor:
            session.exitstatus = 1
        self.receipt = {
            "target": target, "platform": sys.platform, "uid": os.geteuid(),
            "required": sorted(self.required), "passed": sorted(self.passed),
            "failed_or_skipped": sorted(self.bad),
            "collection_bad": self.collection_bad,
            "exitstatus": int(session.exitstatus),
        }
        print("NATIVE_OBLIGATION_RECEIPT " + json.dumps(self.receipt, sort_keys=True))

gate = RequiredCases()
code = int(pytest.main(["-q", "-ra", target], plugins=[gate]))
path = Path(sys.argv[4])
record = gate.receipt | {
    "floor": floor, "process_exitstatus": code,
    "binding": json.loads((path.parent / "native-context.json").read_text()),
}
with path.open("x") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
raise SystemExit(code)
PY
# PG creates its own disposable cluster as UID1001. Root is a separate
# phase; never make the ordinary suite root or silently accept skips.
.venv/bin/python "$native_driver" tests/test_board139_schema_acl_native_20261018.py 6 1001 \
  "$native_evidence/test_board139_schema_acl_native_20261018.json"
sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC "$PWD/.venv/bin/python" \
  "$native_driver" tests/test_node_systemd_pilot_20261018.py 38 0 \
  "$native_evidence/test_node_systemd_pilot_20261018.json"
sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC "$PWD/.venv/bin/python" \
  "$native_driver" tests/native_loadshed_installer_20261030.py 14 0 \
  "$native_evidence/native_loadshed_installer_20261030.json"
sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC YUEBOARD_REPO_PATH="$PWD/.ci-yueboard" \
  "$PWD/.venv/bin/python" "$native_driver" \
  tests/test_schema_contract_receipt_20261020.py 30 0 \
  "$native_evidence/test_schema_contract_receipt_20261020.json"
# These complete modules cover ordinary root/checkout skips. Opt-in is
# explicit; the tests still require Linux root and isolated fixtures.
nginx_lab='nginx@sha256:9bf97bd7714f5e24c1ccd545ecb9eb5435cb6d109c97cebb15e7e455e0239edb'
docker pull "$nginx_lab"
docker tag "$nginx_lab" nginx:1.30.5
test "$(docker image inspect --format '{{.Id}}' "$nginx_lab")" = \
  "$(docker image inspect --format '{{.Id}}' nginx:1.30.5)"
while read -r target floor; do
  sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC YUE_PROTOCOL_RESULTS_NATIVE_LAB=1 \
    YUE_PROTOCOL_RESULTS_NGINX_LAB=1 YUEBOARD_REPO_PATH="$PWD/.ci-yueboard" \
    "$PWD/.venv/bin/python" "$native_driver" "$target" "$floor" 0 \
    "$native_evidence/$(basename "$target" .py).json"
done <<'NATIVE_TARGETS'
tests/test_panel_subscribe_delivery_alert_20261012.py 17
tests/test_frozen_manifest_reader_20261015.py 4
tests/test_status_tls_installer_20261027.py 7
NATIVE_TARGETS
