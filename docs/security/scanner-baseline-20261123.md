# Historical scanner baseline, 2026-11-23

## Workflow findings

Zizmor 1.33.0 emitted one finding across `.github/workflows`. One requires a workflow change.

| Rule | Workflow location | Verdict |
| --- | --- | --- |
| `github-app` (high) | `.github/workflows/policy-ci.yml:146` | Applicable. The mint step disables automatic revocation. The clone step revokes the token on shell exit, but cancellation between minting and entering that step can bypass its cleanup. |

FOLLOW-UP .github/workflows/policy-ci.yml github-app Restore automatic post-job revocation as a fallback and retain early revocation before source execution. Verify cleanup also handles an already-revoked token.
