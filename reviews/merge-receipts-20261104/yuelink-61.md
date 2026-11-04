# yuelink PR 61 exact-source evidence

Source: `b8ee79f9e4100fb6130ada94640fbe4785342ab3`. Independent review is reproduced below. Original parity log: `.claude/state/link-takeover/20261104/1039/release-guard-exact.log`.

```json
{
  "reviewer": "/root/ops",
  "reviewed_at": "2026-11-04T03:29:32.832063+00:00",
  "source_sha": "b8ee79f9e4100fb6130ada94640fbe4785342ab3",
  "base": "95b04a9a327005b5ad87c120f3ecfb8da6c7a43f",
  "verdict": "APPROVE",
  "files": [
    "pubspec.yaml",
    "CHANGELOG.md",
    "docs/releases/v1.3.164.md",
    "docs/releases/v1.3.164.en.md"
  ],
  "checked": [
    "Only version1.3.164+462 and complete bilingual release notes changed",
    "Notes describe independently reviewed delivered behavior; no new product code or publishing claim",
    "Native release guard belongs to lane evidence; this is independent source review"
  ]
}
```

Business source approval preceding the release-only commit:
```json
{
  "reviewer": "/root/ops",
  "reviewed_at": "2026-11-04T03:05:20.480443+00:00",
  "source_tree": "71f713cedac7b0406cea7c885c0b70970572bd02",
  "base": "23fe44ac886f4fa48704d5b3e2bd2b4067ff782a",
  "source_verdict": "APPROVE",
  "release_gate": "Not claimed by review; bind final signed commit and native hook evidence separately",
  "checked": [
    "QUIC chinaips no-resolve and Amazon China direct exclusions match scoped golden updates",
    "Board v2 package preserves historical manifest and adds reset receipt fields",
    "Client DNS live guard uses dedicated client_rules authority, retains historical baseline and rejects empty/malformed inputs",
    "Retired enrollment cannot write through UI or PanelApi allowlist; leave/appeals, historical rewards, wallet and account isolation remain",
    "Shared settings navigation icon retains geometry and uses actionPrimary consistently",
    "Generated orphan deletion reviewed as generated changes; root canonical approval belongs to its assigned reviewer",
    "Final fake clock correction advances two seconds for ceil(now)+1 deadline; actual expiry and parent preservation assertions unchanged. Only this reviewed test differs from prior approved tree."
  ],
  "visual_verdict": "APPROVE for update row in all six supplied Linux screenshots",
  "screenshots": {
    "mine_zh_full_desktop_1440_dark_scale_1.0.png": "07acd1bf0629cb7fb75a35b2029e8ee2ebddd783da7babbe195ae82de62ca936",
    "mine_zh_full_desktop_1440_light_scale_1.0.png": "b3c82eed142be91bd920108c44dc8f8cb4ccc40e6d1af96f77cb08526e7bfff0",
    "mine_zh_full_phone_360_dark_scale_1.0.png": "c1a82811a6c790b0ea55a790b8b58ad57279bffde71de6dc003729bd34018343",
    "mine_zh_full_phone_360_light_scale_1.0.png": "5d633816497191dd85f63edd77b51aa4181b748441c50d607beed23e46229769",
    "mine_zh_full_tablet_768_dark_scale_1.0.png": "60810a8bd315029c39c96e3c8b146d4435ecd95960ceff473bd181a29d5ccc57",
    "mine_zh_full_tablet_768_light_scale_1.0.png": "d1b7f7a483dc30b8a3311b08e473cf4ffad13a1daa3223939c26828ebf53b293"
  },
  "withdrawn_finding": {
    "claim": "tablet768 dark renewal button appeared blank in scaled preview",
    "resolution": "Retracted after original-size inspection: white icon and renewal text are fully visible at x385 y249. No source fix or new screenshot is required.",
    "sha256": "60810a8bd315029c39c96e3c8b146d4435ecd95960ceff473bd181a29d5ccc57"
  },
  "formatter_delta": "Compared with 2dada895: one PanelApi allowlist changed to a single line; whitespace only.",
  "source_sha": "95b04a9a327005b5ad87c120f3ecfb8da6c7a43f",
  "final_bound_at": "2026-11-04T03:19:31.507463+00:00"
}

```
The parity log proves the exact-source release guard only. Full native hooks and Linux evidence remain in the recorded lane evidence; skipped cases are not counted as passed. No publication is claimed.
