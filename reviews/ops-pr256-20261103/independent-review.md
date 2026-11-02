# Shared-input review of yueops #256

Reviewer: Codex, source-diff and admission-policy review in this session; no separate independent reviewer was invoked. The historical evidence field name is retained.

Adds sqlglot 28.0.0 to the test group (and inherited dev group). The lock format revision changes from 3 to 5. Existing package records are unchanged, including Langfuse 4.18.0 inherited from #122. The PR also adds schema policy, documentation, a CI check and a test module outside shared inputs.

VERDICT: APPROVE exact shared-input successor only. No runtime execution, dependency safety audit, full collection or production qualification is claimed. Required merge order: pinned master, #122, #256.
