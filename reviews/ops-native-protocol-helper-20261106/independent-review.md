# Independent exact native protocol fixture admission review

VERDICT: APPROVE

Reviewer: /root/integration_review. Approved path: tests/native_protocol_fixture.py in onesyue/yueops. Exact Git blob: 332451694efa7a9daa29c407e63c5e94fc4adbfb. Mode: 100644. Introduced by 118b87f30; present unchanged in independently reviewed HY2 candidate 8ca25190ab028fc0210ae1bfc9649fd9672f8a3b and current integrated release pin d4880f37a7a9a3dbc9b6d32a16125745691fb88e. Read-only Git ancestry check confirms the introducing source is an ancestor of the integrated pin.

Read the complete thirteen-line helper. It returns fresh synthetic dictionaries for keyed HY2, WS/TLS and TCP/REALITY/Vision test profiles. It contains only fixture credentials and example names, has no file/network/production side effect, and does not skip tests, patch validators or swallow failures. The default branch preserves the test fixture's VLESS shape; this helper is not production protocol validation.

The exact direct consumer set found in the integrated source is:
- tests/test_relay_topology_history_20261009.py
- tests/test_native_entry_pairs_publication_20261009.py
- tests/test_relay_topology.py
- tests/test_native_protocol_protection.py
- tests/test_bucket_native_legacy_ports_20261013.py

Each imports and actually calls protected_settings to populate the real tested topology/publication/protection input. The helper supplies well-formed positive baselines; the protection module mutates them for negative cases. No production imports or expanded source scope are approved by this receipt.

Reuse the already-reviewed HY2 ops/review.md and final-results.json under .claude/state/hy2-diagnose/20261106/code-0733: exact final 8ca source had 1121 cases, 1066 passed, 55 explicit environment skips, plus 51 UID0 IPv6 and 52 native-buffer passing supplement cases. This is existing bounded module evidence, not a full release pass. No test was rerun for this review.

Admission may recognize only this exact new helper blob/mode at the validated current pin, with source ancestry and a sealed copy of this review. It must preserve every pre-existing common input and historical PR256/PR122 seal; no unknown helper, mode change, different bytes, missing consumer or relaxed source binding is covered. All 52 same-run native obligations and actual execution obligations for the five consumers remain unchanged. Full CI candidate logic requires its own review and negative controls.

No source, Git state, credentials or runtime were changed by this reviewer.
