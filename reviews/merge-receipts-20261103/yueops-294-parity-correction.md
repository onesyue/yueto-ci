# Correction: yueops #294 receipt parity result

merge-receipts/yueops/294.json records `parity.result: "pass"` at head 79a20284.
The referenced log (yueops-294-parity.log) actually shows **2 failed**, 610 passed, 22 skipped:

- test_hy2_creation_default_transaction::test_lock_busy_never_bypassed_and_first_lock_released
- test_node_hy2_only_consumers::test_agent_reports_slot_layout_and_the_sanitizer_keeps_it

Both fail identically on master 9f06d9f1 (pre-existing, not introduced by #294), but the
truthful classification is "no new failures vs master", not "pass". The receipt JSON is left
unchanged so admission evidence for the shipped head is not broken; this note is the
authoritative correction. Follow-up: fix the two pre-existing failures in yueops.

Recorded 2026-11-03 by the coordinator lane.
