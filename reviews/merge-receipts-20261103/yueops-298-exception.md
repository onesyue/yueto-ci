# yueops #298 — exception evidence (no regression vs base)

head: 837675c2e2cb89676a386a6034c302e46476a80b
base: 79a20284eb1947f84dd663ac743ff5d2a7cd1c64
runner: box, 2026-11-03 SGT; full suite at head earlier ended EXIT 1 (7-8 failed, 7 errors).
Re-ran the full-suite failure set on head and base with the same venv:
- head: 7 failed, 7 errors, 1 passed (14 failures)
- base: 8 failed, 7 errors (15 failures)
- failures on head not on base: 0. Extra base failure is a known flaky (ticket_worker bounded retry; also failed once on head in a full run).

PARITY: NOT pass. Recorded as exception: no regression vs base.
head log sha256: 05775be5f8b830a890684089be11aaae54a26b13755febfa25f534610bf616c3

## Failing on both head and base
- tests/test_ai_cs_capabilities.py::test_live_support_copy_has_no_handoff_wording
- tests/test_botyue_source_readability.py::test_verify_consumer_imports_root_package_in_isolated_python
- tests/test_delivery_source_pins_match_the_repo_20260916.py::test_every_pinned_repo_file_hash_is_current[rebind-operator-units.py]
- tests/test_device_limit_authoritative_counts_20260923.py::test_negative_account_device_limit_uses_plan_on_disposable_postgres
- tests/test_native_postgres_socket_20260925.py::test_tcp_fixture_overrides_unwritable_socket_default_and_reports_failure
- tests/test_node_slo_rereview_pg.py::test_catalog_runtime_grants_and_scheduler_failure
- tests/test_node_slo_rereview_pg.py::test_compensation_retries_preserve_calculation_and_terminal_state[approve]
- tests/test_node_slo_rereview_pg.py::test_compensation_retries_preserve_calculation_and_terminal_state[skip]
- tests/test_node_slo_rereview_pg.py::test_concurrent_compensation_approvals_return_one_durable_result
- tests/test_node_slo_rereview_pg.py::test_json_config_insert_update_plan_and_approval
- tests/test_node_slo_rereview_pg.py::test_lost_hide_response_survives_session_restart[False]
- tests/test_node_slo_rereview_pg.py::test_lost_hide_response_survives_session_restart[True]
- tests/test_role_grant_manifest_generated.py::test_generated_manifest
- tests/test_yueboard_schema_migrator_contract_20260731.py::test_exact_release_pin_matches_the_reviewed_yueboard_release_bytes
