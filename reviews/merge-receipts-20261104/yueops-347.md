# Independent review: yueops #347

Head: bf8d0ec70cd0aa32893483d7bbc1e57efbf8b75c
Parent: 80f7c8e6589c68eefa88aff25cad2e1f55e17350
Reviewer: codex (independent RC1104 review lane)
Reviewed at: 2026-11-04T12:42:08.623092Z

VERDICT: request_changes

## Finding

P2 — Preserve DHCP rollback when persisting the failed-attempt timestamp fails.
`scripts/direct-ip-rotate.sh:390` adds an immediate exit on `write_state` failure before the existing original-identity restoration. If the provider has already changed the interface MAC, polling still observes the previous address, and the subsequent state write fails (for example, storage exhaustion), this new exit leaves the changed identity installed. The rescue timer is insufficient in that case: `dhcp_rescue` restores the identity only when the interface has no global IPv4 address. A same-address response with a global address skips that repair. The parent attempted identity restoration for this path. Retain the failure exit and durable precharged budget, but attempt the required identity restoration regardless of whether completion-time persistence succeeds.

## Scope and evidence

Read all five changed files versus the exact first parent and the surrounding budget, locking, DHCP restoration, rescue and state-write implementation. The central path retains pre-attempt charging and its lock; the changed boundary tests cover three attempts and completion-time backoff. `git diff --check HEAD^ HEAD` returned 0. This is source review, not installed behavior or production validation. No source was changed.

Full requested Mac parity is recorded separately in `parity-logs/20261104/yueops-347.log`. A failed or incomplete run is not passing parity. No merge receipt is authorized by this review.
