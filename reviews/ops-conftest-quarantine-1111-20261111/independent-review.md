# Independent exact shared-input transition review

VERDICT: APPROVE

Reviewer: closeout executor (box), read-only source review. I did not write either source commit. Scope is this exact blob change only. It is not a full runtime gate and not the later image ship.

Source before: d2129d5993ad977b7b51bf92ac6da477fdd0e531 (live yueops).
Source after: 5c4cc83a7ae52aa888f1079a66eaaf9c16714be4 (master, ship 9 candidate).
Path: tests/conftest.py. Before blob bdf05f9d2e1122e903e4b80d07c8e0ff2d315f55, after blob 3776755a872e2919f9ca3360fb9a4c630b5b2ec8. Mode stays 100644.
Commits touching it in the range: a8bdd4684 and 5c4cc83a7. No other shared input changed (admission-precheck lists only this path).

What the diff does:
- Adds stdlib imports `stat` and `tempfile`.
- At import, writes one temporary JSON file with an empty retired-entry list (mode 0644) and forces YUEOPS_RETIRED_ENTRY_QUARANTINE to it, so existing DNS writers stay allow-all in tests. Production still fails closed when the variable is unset and the bastion file is missing.
- The autouse `_restore_credential_env` fixture also restores that variable and rewrites the same empty document before and after each test, refusing to write through a planted symlink (O_NOFOLLOW, unlink of a symlink).
- `_isolate_env` sets DIRECT_GFW_DOMESTIC_PROBE=0 so copied environments never call Globalping.

What it does not do: no new or changed pytest hooks, markers, skip or xfail logic, collection rules or plugins; no subprocess or network at import or in fixtures. Collection membership is unchanged. The only import-time side effect is the one temporary file and one environment variable, recorded in qualification.json.

Read source-freeze.json and qualification.json in this directory. The qualification claims static shared-input qualification only and says the full gate was not run. This approval admits only the exact blob transition above. It does not rewrite earlier seals, waive native obligations or replace same-run execution receipts.

No source, Git state, production data or credentials were changed.
