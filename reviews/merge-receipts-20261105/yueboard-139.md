# yueboard #139 review at 08bf94184af24ebcc9f4af036cd7027fbf397cdb

VERDICT: approve

- Conditional on yueboard #141 (`3bf5cf82`) shipping in the same release: the retired `status-write` scope is discarded without invalidating surviving permissions; unknown scopes still fail closed. `internal/modules/nodesync/yueops_scoped_token.go:284-299`. (Bullet restated by the coordinator; the original wording was dropped by the secret-word filter.)

- Only the two intended endpoints disappear; all 77 surviving scope mappings, other endpoints, auth gates and protected paths remain unchanged. `internal/modules/nodesync/internal.go:36`, `internal/modules/nodesync/yueops_scope.go:55`.
- No runtime callers or remaining handler references found across Board and the five consumer roots. Nonblocking stale documentation remains: `yueops/docs/runbook/fleet-reconcile.md:122`.
- Public status reads remain; existing snapshots eventually become unknown without new samples. `internal/modules/guest/guest.go:146`.
- Static review approval only; tests were not rerun. Existing evidence records incomplete full-suite/Linux gates. `docs/audits/ybdead-20261104.md:111`.
