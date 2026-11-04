# yueboard PR129 exact-head acceptance evidence

Head `a751ea8a652a2cef888b2416f4a7f8e617eab7e2`. Original raw log: `.claude/state/template-corpus/20261104/c1/linux.log`. Copied bytes and SHA-256 are unchanged; run time is the original log modification time.

Both host/Linux passed12 real render rows and6 identity rejection cases, zero skips. Twelve hashes and four exported artifact bytes match. This is Board rendering/structure only; client/core/parser/online-provider execution remains separate.

Independent review:

```json
{
  "reviewer": "/root/board",
  "reviewed_at": "2026-11-04T05:15:12.370215+00:00",
  "decision": "APPROVE_SOURCE",
  "base": "477d3c9a7e7ccaa16941686d0d0e5b65c27111d8",
  "candidate": "Signed exact15-file snapshot",
  "files_sha256": {
    "internal/modules/subscribe/frozen_template_corpus_test.go": "48e8d56d68a70a6a51f6571c7dd869d9b59d6b56f47db1c006f0eebe258b2662",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/README.md": "22f2373ee657cca2dca9da9993f9f09102a453c92f311b8e7e10b78765a616ec",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/clash.en.yaml": "954887c4d4ca5db80d36434813a3f5e6c32c44dc0225796d3096196fc9a45d03",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/clash.zh-CN.yaml": "cc6629ebd9f7d7c538778efb2d9da0b2550f0febb69be4892f6a78a20bdf06af",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/clashmeta.en.yaml": "5f32d36c30335b578c333ab529d1c470b0452236fbdd982a0729d7573e5dafa4",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/clashmeta.zh-CN.yaml": "6cbe25a83381f54fca80bbfdfa19e2679a68aa447e7967a09ee8b66b2f607b24",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/manifest.json": "6eeeae5cc2a73689d08d206480a0b58d504a673ac96da60f025b4edf1df50bb0",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/singbox.en.json": "83e54a22d86b1ef00932395312dde4568cb0fafbc9316b0a3bc710f4cd12057b",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/singbox.zh-CN.json": "94bfcdae85efbb098ec46057fa10434b7d608344cfd855bf517f0cdfbd58f5c3",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/stash.en.yaml": "ee4a96bca7dfb5251186b3c347571441f1fbbbe0d546dd927f41560d9bc2ed7c",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/stash.zh-CN.yaml": "726f5a8f735fc547284a6e5ff3c15fa1e1b3cb36e91f4de71f201939e97c0a97",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/surfboard.en.conf": "24b241c85164f0d444b961034a5bcb27877a231d0057be7c135bae0854d50118",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/surfboard.zh-CN.conf": "eb8ade713ddf2057b4470175734442c88c08e04d1bc23d7fa3a473b642a81e39",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/surge.en.conf": "56eb0a037ba59680cc0f64e1cdc768c225fd484f7d8ae969a97df16d76885e1d",
    "internal/modules/subscribe/testdata/frozen_templates_20261104/surge.zh-CN.conf": "ba4a89af344f3353da521ecacc450ef0f4e5e7b8d6d47ddfbf3d3bc87ee133ca"
  },
  "snapshot_sha256": "b8ff96ae3c53ea7edf9c659d8424799165d828f2c3f9173580590c5e3dd91a7e",
  "findings": [
    "Copied manifest byte-identical to root26a145 manifest, SHA6eeeae5c; all12 fixtures match exact desired hashes. Six-format/two-locale closed universe plus length12 and uniqueness prevents missing identity admission.",
    "Real Module renderClashMeta/renderSingBoxForClient/renderSurge/renderSurfboard called with explicit locale context and English cache key. Synthetic account/node/settings fixtures avoid DB/network; this is renderer coverage, not HTTP/auth/DB acceptance.",
    "Six identity mutations reject missing row, duplicate, unknown format/locale, missing file and byte corruption. Positive case requires12 outputs and emits no success manifest after failed subtest.",
    "Four downstream outputs exported only for clashmeta/singbox; manifest records12 input/output hashes and explicit declared capability/proprietary limitations.",
    "Structured YAML/JSON group/proxy membership and INI section/group checks are structural checks, not mihomo/sing-box/proprietary parser execution. Providers are not fetched; scope explicitly prohibits interpreting absent providers as online policy coverage."
  ],
  "tests": "Existing author ready.json: host/Linux each12 render+6 negative, 0skip; four exported artifact hashes match. No reviewer rerun.",
  "limitations": [
    "No core execution, effective DNS, live routing, client transformation, or service-IP route acceptance claimed.",
    "Signed Board source and actual toolchain/run receipts must accompany exported output hashes."
  ],
  "signed_head": "a751ea8a652a2cef888b2416f4a7f8e617eab7e2",
  "tree": "2d39ac51e156e1947ad72def4238e0ce26cecb9d",
  "signature": "G",
  "bound_at": "2026-11-04T05:19:19.770045+00:00"
}
```

Supplemental original receipt:

```json
{
  "owner": "Board C1 corpus lane",
  "recorded_at": "2026-11-04T05:17:59.290491+00:00",
  "worktree": "/Users/j/Projects/yueboard-c1-template-binding-1104",
  "branch": "codex/c1-template-binding-1104",
  "base": "477d3c9a7e7ccaa16941686d0d0e5b65c27111d8",
  "commit": "a751ea8a652a2cef888b2416f4a7f8e617eab7e2",
  "tree": "2d39ac51e156e1947ad72def4238e0ce26cecb9d",
  "signature": "G",
  "source_hashes": "source-hashes.json",
  "host": {
    "log": "host-final.log",
    "renders": 12,
    "negative_cases": 6,
    "skips": 0,
    "go": "go1.27.3 darwin/arm64"
  },
  "linux": {
    "log": "linux.log",
    "renders": 12,
    "negative_cases": 6,
    "skips": 0,
    "go": "go1.27.3 linux/amd64",
    "image": "sha256:cf320c534782414c6e047c7d79b7c3a1f31433c5e4774c5889d43df525030e48",
    "network": "none",
    "timezone": "UTC",
    "source_archive_sha256": "b704a663e143bf750422a876afa90e95fd8db1b6fa0fec93e0cbde70fb3aa04c"
  },
  "parity": "All twelve output hashes and all four exported artifact bytes match between host and Linux. Frozen archive matches fifteen committed source/fixture hashes.",
  "artifacts": "artifacts/render-manifest.json",
  "static": "gofmt, gopls CLI, Go test vet passed; exact Chinese input trailing blank lines retained for SHA identity",
  "review": {
    "decision": "APPROVE_SOURCE",
    "reviewer": "/root/board",
    "receipt": ".claude/state/board-takeover/20261104/resume-1039/board-c1-frozen-corpus-review.json",
    "signed_head": "a751ea8a652a2cef888b2416f4a7f8e617eab7e2",
    "bound_at": "2026-11-04T05:19:19.770045+00:00",
    "matched_files": 15
  },
  "scope": "Board renders only. Client transformation/pinned core parsing and live provider execution remain pending; missing providers offline-only. No production edits or deployment.",
  "delivery": "Pushed origin/codex/c1-template-binding-1104 at a751ea8a652a2cef888b2416f4a7f8e617eab7e2; no master merge or deployment.",
  "pull_request": {
    "url": "https://github.com/onesyue/yueboard/pull/129",
    "number": 129,
    "draft": true,
    "stacked_base_pr": 128,
    "head": "a751ea8a652a2cef888b2416f4a7f8e617eab7e2",
    "readback": "Exact head/base read back by Board agent, confirmed by coordinator handoff; not queried again by this lane."
  },
  "handoff": {
    "source_custody": "Frozen and released by coordinator; no further source writes assigned.",
    "downstream": "Four artifacts transferred to CN thread for sequential C1 consumer then C2 work.",
    "evidence": "Retained; no cleanup, retest, source edit or release operation."
  }
}
```
