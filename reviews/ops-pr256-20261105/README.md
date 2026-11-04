# #256 strict shared-input successor

This candidate supersedes the earlier relaxed proposal. The original admission functions and synthetic continuity fixture are restored. Only the #256 seal registrations remain in the planner diff.

The transition starts at #122 source_after `56a7e0412e9bd1d297ba4a5dd3d363147fac463c` and ends at `4b64bf9a9b26a24aecdc551bbe7eaa7a840558cd`. No intervening commit changes either shared path; only the final #256 commit does. Historical seals and baseline files remain untouched. The source freeze, static qualification, review hashes and seal identity are recomputed for this strict transition.

Following a54f551, only source_revision in ops-first-native-successors.json is repinned to `72bf60474359d831f0cee70a6246ebf50952ea26`.

Run `python3 reviews/ops-pr256-20261105/qualification-driver.py /path/to/yueops`. It creates a disposable clone, executes the real scripts/pytest-shards.py expand CLI with the on-disk policy, ubuntu-24.04 runner, capacity 20 and 16 shards, and returns its exit code. Workflow identity labels are local simulation values; this is not Linux runtime qualification. A read-only trace diagnoses refusal without changing policy or admission decisions.

Current result: REJECTED (exit 1), shared collection/dependency input modes changed. The effective map contains tests/p015_offline_plugin.py (100644) absent from the historical map. Every existing historical mode equals the target ls-tree mode. The extra helper was introduced by fcd5a5ee4ba44550911b9f8ed6463d388821116d and its target blob is 396456b1fd3fd2066de2a69be144525a62d2c63a. shared_inputs includes non-test Python helpers under tests/. No active transition peels this path. Neither 077a1ee nor a54f551 supplies an existing registration for it; adding one requires new reviewed admission logic, forbidden by item 1. Historical modes cannot be edited. Thus no strict path exists within this task's permitted changes.

admission-results.json and current-policy-admission.log are the current CLI evidence. strict-all-seal-tests.log and strict-build-policy-tests.log are the current test evidence. Older logs without the strict prefix belong to the superseded attempt and do not qualify this candidate. The initial CLI invocation without local workflow identity failed at startup with workflow policy identity differs; the corrected driver supplies that context explicitly.

The sealed independent-review.md is explicitly a same-session source review, not an independent review claim. Independent code review of this strict candidate is recorded separately in strict-review.md and the run report.
