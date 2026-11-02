APPROVE_WITH_NOTES

- `scripts/validate-yueboard-postgres.py:37`: Reasonable capability-based correction. It does relax deletion protection: removing or renaming `worker.go` alongside the suite removes the requirement, even at floor ≥150. Discovered suites remain mandatory per the stated contract.
- `tests/test_postgres_integration_gate.py:389`: The negative stderr assertion can pass on unrelated failures. Assert the expected successful outcome as well.
- Review limited to the supplied diff; no executable checkout available. The reported PyYAML failure fixed by #58 is a separate CI issue.
