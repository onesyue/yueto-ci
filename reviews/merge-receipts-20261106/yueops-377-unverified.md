# Ops PR377: unverified historical receipt

The adjacent JSON preserves the original malformed receipt byte for byte.
It is historical evidence, not an accepted merge receipt. The active receipt
path is intentionally absent so the unchanged audit reports missing evidence
instead of stopping at a malformed record.

Authenticated GitHub read on 2026-11-06:

- PR: https://github.com/onesyue/yueops/pull/377
- Actual head and merge: `4334122aaaad56258ecb8a33c4263f2fd9c2be95`.
- Base: `5a014e5664cc127e37686edd9c7d0324d213a468`.
- Merge time: `2026-11-04T23:56:37Z`.
- Reviews, issue comments and head check-run queries returned empty lists.

The original receipt instead binds its head, review and parity to the base
commit and points to the PR374 review. Its extra `head_sha` field names the
actual PR377 head but does not establish review or test execution for that
head. The referenced PR374 artifact explicitly covers commits `602a7b37b` and
`5a014e566`; it cannot certify PR377's subsequent LoadUnit change. The original
source commit `d92e2f7ea05c6b05366fa6837b8e905492b0db67` remains in Git history.

No original PR377 approval or exact-head parity transcript was recovered from
the bounded worktree, task evidence and GitHub checks. Current review/test
results cannot be relabeled as evidence from the original 24-hour receipt
window. Historical approval and CI parity therefore remain UNKNOWN, and the
existing audit policy is unchanged.

Original JSON SHA256: `6aff628e6b562a661874120027c05a5a022a5a75b63a86ec7941b3f7ca53acfd`.
