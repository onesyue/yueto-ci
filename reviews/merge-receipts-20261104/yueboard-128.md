# yueboard PR128 exact-source evidence

Head `477d3c9a7e7ccaa16941686d0d0e5b65c27111d8`. Original command-output log: `.claude/state/board-takeover/20261104/ui-b1/la-r2.log`. The copied log retains original bytes. Independent source review and supplemental evidence follow. They do not imply publication or production acceptance.

```json
{
  "reviewer": "/root/link",
  "reviewed_at": "2026-11-04T04:24:42.794691+00:00",
  "repository": "/Users/j/Projects/yueboard-ui-b1-1104",
  "base": "ba838b22bc7dc80190662855eb6439bc8b28c73c",
  "head": "477d3c9a7e7ccaa16941686d0d0e5b65c27111d8",
  "verdict": "APPROVE",
  "scope": "Source only: account-journeys.spec.ts twelve-case real admin users directory matrix. Browser execution and screenshots remain pending; no release acceptance implied.",
  "findings": [],
  "checks": [
    "Uses actual register/login/MFA, PostgreSQL and backend APIs; no success response interception.",
    "List response bound to exact search body, seeded ID/email and real row URL; detail response bound to requested ID and exact identity.",
    "Real users route, POST fetch API and GET getUserInfoById wiring verified in web-admin source.",
    "Both locales/themes and360/768/1440 named in unique screenshot filenames; font/transition wait and horizontal overflow assertions precede captures.",
    "pageErrors fixture fails in teardown; only the existing exact ViewTransition exemption remains.",
    "Reload/detail and back/search checks preserve identity and query; global workers1/fullyParallelfalse avoids shared-database/TOTP concurrency within suite.",
    "Follow-up5a589\u2192477 uses actual admin language menu instead of unsupported query override, and scopes reload email to the real Overview tabpanel while preserving exact seed/API/ID checks. First-run12 new failures remain failed evidence; runtime rerun remains pending."
  ],
  "not_executed": [
    "Pinned Linux twelve cases",
    "Independent actual image review"
  ]
}
```

Original supplemental artifact: `.claude/state/link-takeover/20261104/ui-a/board-ui-b1-visual-review.json`

```json
{
  "verdict": "APPROVE",
  "reviewer": "root/link independent reviewer",
  "reviewed_at": "2026-11-04T04:36:22.397257+00:00",
  "head": "477d3c9a7e7ccaa16941686d0d0e5b65c27111d8",
  "scope": "UI-B1 real admin users search results and user detail screenshots",
  "method": "Individually inspected all 24 original PNGs; verified local bytes against supplied manifest. No rerun or image modification.",
  "coverage": {
    "widths": [
      360,
      768,
      1440
    ],
    "locales": [
      "en",
      "zh-CN"
    ],
    "themes": [
      "light",
      "dark"
    ],
    "states": [
      "list",
      "detail"
    ]
  },
  "findings": [],
  "observations": [
    "Text and controls are legible in both themes. Real English and Chinese locale selection is visible. List result IDs and detail IDs match within each pair. Long emails wrap in detail cards; list cell ellipsis and bounded table scrolling preserve layout.",
    "Only captured list and detail states are approved. Unopened menus and dialogs are not visual evidence."
  ],
  "writer_test_evidence": "la-r2.log: 14 passed, 0 skipped; reused, not independently rerun",
  "screenshots": [
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-04a4a-arget-\u00b7-zh-CN-\u00b7-dark-\u00b7-1440/directory-detail-zh-CN-dark-1440.png",
      "sha256": "f4acd714da17878cf567e68a1e577994b65ba7cc2ab2a83cd194d4b88329788a",
      "bytes": 156603
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-04a4a-arget-\u00b7-zh-CN-\u00b7-dark-\u00b7-1440/directory-list-zh-CN-dark-1440.png",
      "sha256": "2dd398deeed942b241eb40c6b81be8145f266859e2d31c162b6ed888cc851a98",
      "bytes": 104486
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3024f-o-target-\u00b7-en-\u00b7-light-\u00b7-768/directory-detail-en-light-768.png",
      "sha256": "0e4614f3b6239a8ed76de825cf26e90e1a7772612d3d0375bce74ed4137a1a46",
      "bytes": 112796
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3024f-o-target-\u00b7-en-\u00b7-light-\u00b7-768/directory-list-en-light-768.png",
      "sha256": "fccb58d2ccbed7d0933870dee9e6d122b89847b958f521234b3089db3e570165",
      "bytes": 59656
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3b387-o-target-\u00b7-en-\u00b7-dark-\u00b7-1440/directory-detail-en-dark-1440.png",
      "sha256": "ca70208aa87ada2b08c4d37517f953849df9ba2ea0765d1c1004e909fa86d032",
      "bytes": 147642
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3b387-o-target-\u00b7-en-\u00b7-dark-\u00b7-1440/directory-list-en-dark-1440.png",
      "sha256": "0c08926b64acd20a568956537777e1115dd984cf65772764c6cbb98365e4cba6",
      "bytes": 98719
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3e885-arget-\u00b7-zh-CN-\u00b7-light-\u00b7-360/directory-detail-zh-CN-light-360.png",
      "sha256": "07456cefdae46c68b6656705156d8f2a399c5eaaaff8660e7a78fa1b57ff932f",
      "bytes": 117414
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-3e885-arget-\u00b7-zh-CN-\u00b7-light-\u00b7-360/directory-list-zh-CN-light-360.png",
      "sha256": "5f46befd8a33bd3bfca84c12dc8028b6d59027e43f2abe13ba43c8ceeb6ff6f7",
      "bytes": 50039
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-9affc-to-target-\u00b7-en-\u00b7-dark-\u00b7-768/directory-detail-en-dark-768.png",
      "sha256": "ee8c70029d781d18ccc7f04e570aab477895cd46110fef312230c94fdd4bf7be",
      "bytes": 113404
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-9affc-to-target-\u00b7-en-\u00b7-dark-\u00b7-768/directory-list-en-dark-768.png",
      "sha256": "ebf5b0d290f9ec50df28d36c0eec2fb88663660decf60d8437b9a0345eba1a00",
      "bytes": 58782
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-a90e4--target-\u00b7-en-\u00b7-light-\u00b7-1440/directory-detail-en-light-1440.png",
      "sha256": "454fca362bfdb3126cbd8d67b3884cdc902b27f359319359b550c598cfaec9d3",
      "bytes": 145914
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-a90e4--target-\u00b7-en-\u00b7-light-\u00b7-1440/directory-list-en-light-1440.png",
      "sha256": "238a4e5af992a52066d731b4d2c310eb66ea3124c6be8151ea9aa7f5d53f54b9",
      "bytes": 98993
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-b24b5-to-target-\u00b7-en-\u00b7-dark-\u00b7-360/directory-detail-en-dark-360.png",
      "sha256": "2f916d8d1bb94a0eaa88ef171abd6819ffe57122ef367a5715cb35310080da43",
      "bytes": 115865
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-b24b5-to-target-\u00b7-en-\u00b7-dark-\u00b7-360/directory-list-en-dark-360.png",
      "sha256": "ee61848935f6bc5b047c74cbc4cc6b6285df5aca9846abf99756ba35806d5677",
      "bytes": 47416
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-b83dc-target-\u00b7-zh-CN-\u00b7-dark-\u00b7-360/directory-detail-zh-CN-dark-360.png",
      "sha256": "07175f28226953d81788937fda8fe1772615941c8c8e6e4a46519f1b80aa915a",
      "bytes": 118605
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-b83dc-target-\u00b7-zh-CN-\u00b7-dark-\u00b7-360/directory-list-zh-CN-dark-360.png",
      "sha256": "f2fecec1c635573a41c4b7cf31a5c4c8ce6cd771e9ee308ecfedb8cea90b1775",
      "bytes": 49969
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-cb0c3-o-target-\u00b7-en-\u00b7-light-\u00b7-360/directory-detail-en-light-360.png",
      "sha256": "88cf9c2d6b511d362d27161b954bb8525aee19d8a4dabe8614552e8c74f18e61",
      "bytes": 114244
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-cb0c3-o-target-\u00b7-en-\u00b7-light-\u00b7-360/directory-list-en-light-360.png",
      "sha256": "9047efd07cd43e4cb2cfff310de5a2e347701d9c3780e8daee52cd2b40cc2cb2",
      "bytes": 47916
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-e26e1-target-\u00b7-zh-CN-\u00b7-dark-\u00b7-768/directory-detail-zh-CN-dark-768.png",
      "sha256": "4ac006105d3709eb22f30214e6bba6812f61322f035d5ec74aa763edaee77950",
      "bytes": 120698
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-e26e1-target-\u00b7-zh-CN-\u00b7-dark-\u00b7-768/directory-list-zh-CN-dark-768.png",
      "sha256": "0aff078ff4438d36a31bb05331a9a0a2a66f0280637398d0404f59c6b259f500",
      "bytes": 62569
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-fc426-rget-\u00b7-zh-CN-\u00b7-light-\u00b7-1440/directory-detail-zh-CN-light-1440.png",
      "sha256": "851067217e92bdd5dbda0ab40a0bbbf22d66e07b33d4835ae9641ed1fe0b0391",
      "bytes": 155152
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-fc426-rget-\u00b7-zh-CN-\u00b7-light-\u00b7-1440/directory-list-zh-CN-light-1440.png",
      "sha256": "e267e924d20cd5921b01b9c9627d29459712fcafe9e6da75e321193028f79d26",
      "bytes": 104319
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-fce1f-arget-\u00b7-zh-CN-\u00b7-light-\u00b7-768/directory-detail-zh-CN-light-768.png",
      "sha256": "e852cf7d41c09de34eea5489d0dec61bf41eea8e65c2573512039f3ba414f29f",
      "bytes": 119223
    },
    {
      "path": "artifacts/test-results/account-journeys-UI-B1-rea-fce1f-arget-\u00b7-zh-CN-\u00b7-light-\u00b7-768/directory-list-zh-CN-light-768.png",
      "sha256": "aa3d8d5fb0c659364a5748175e5347b73af7b20ed43edcfaa5292580af1eabf9",
      "bytes": 62835
    }
  ]
}

```

Original supplemental artifact: `.claude/state/board-takeover/20261104/ui-b1/la-r2-proof/terminal.json`

```json
{
  "exit_code": 0,
  "phase": "tests",
  "finished_unix": 1793766602.8607287
}
```

The native Linux run passed14 cases (12 new and2 existing) with no skips;24 original screenshots were independently approved. The first failed fixture run and incomplete optional local failure-archive copy remain recorded; complete originals are retained remotely.

## Native exit and redundant outer cleanup

The original log ends with a Docker network-not-found message and an exit-status-1 line from the outer launcher’s redundant cleanup. The launcher uses `check=True` for the complete native command and sets its test-phase result to zero only after that command returns successfully. Its `finally` cleanup invokes the second network removal without checking the result; the native EXIT trap already removed the network. The original terminal receipt records test phase exit zero. Thus the native command and its 14 browser cases passed; the redundant outer cleanup emitted a nonzero diagnostic. The raw log, including that diagnostic, is retained unchanged. Independent reviewers confirmed this from the existing launcher and terminal receipts without rerunning tests.

- `.claude/state/board-takeover/20261104/ui-b1/remote-run-r2.py` SHA-256 `91547f3393f5f7f39e261d883293954f155aada0194295ae18ef30c68ea3353c`.
- `.claude/state/board-takeover/20261104/ui-b1/la-r2-proof/terminal.json` SHA-256 `2bbaf761885efbdddb876d0637290603ff36e7986a4336e4bde6f42566c39446`.

Original terminal receipt:

```json
{
  "exit_code": 0,
  "phase": "tests",
  "finished_unix": 1793766602.8607287
}```
