# Historical scanner baseline, 2026-11-23

## Workflow findings

Zizmor 1.33.0 emitted one finding across `.github/workflows`. One requires a workflow change.

| Rule | Workflow location | Verdict |
| --- | --- | --- |
| `github-app` (high) | `.github/workflows/policy-ci.yml:146` | Applicable. The mint step disables automatic revocation. The clone step revokes the token on shell exit, but cancellation between minting and entering that step can bypass its cleanup. |

FOLLOW-UP .github/workflows/policy-ci.yml github-app Restore automatic post-job revocation as a fallback and retain early revocation before source execution. Verify cleanup also handles an already-revoked token.

## Historical secret findings

Gitleaks 8.30.1 reported 107 historical findings across 13 commits before the baseline. The rules were `generic-api-key` (99), `sourcegraph-access-token` (7) and `cloudflare-api-key` (1). Each reviewed occurrence has its own commit, file, rule and line fingerprint in the repository's `.gitleaksignore`.

| Count | Evidence and disposition |
| ---: | --- |
| 89 | The source-freeze manifests, policy admission log and pytest skip baseline map test file paths to content digests or Git object IDs. The Cloudflare match is the object ID for a Cloudflare IP refresh test file. |
| 9 | The YueBoard review receipt reproduces eight parser or normalization test inputs and one constant assigned to a synthetic subscription benchmark server. |
| 7 | The YueOps build receipt records a checkout revision and upstream tool revisions in archive URLs, module hash checks, module output and build metadata. |
| 1 | The root review receipt lists the generated internationalization check as a command argument following the design token check. |
| 1 | The pytest sharding script uses a string constant as a dictionary key to look up and remove a retired baseline record. |

**ROTATE-NEEDED:** 0.
