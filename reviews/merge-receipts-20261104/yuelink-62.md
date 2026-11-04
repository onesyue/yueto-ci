# YueLink PR62 exact-source review

DONE UI-A original-image review completed. APPROVE for the finite local Profiles contract.

# UI-A Profiles independent review — 2026-11-04

Owner: independent UI-A reviewer, delegated by coordinator `01a1a469-81cc-75f3-baa3-7394a3901519`. Sole writable artifact: this receipt. No source edits, screenshots regenerated, or tests rerun by this reviewer.

## Contract and verdict

The finite UI-A contract in `docs/2026-10-17-whole-estate-execution-plan.md:1857` requires actual route coverage at widths 360/768/1440, both themes, loading/error/empty/long text, no overflow, legible actionable controls, and independent original-image review. Verdict: **APPROVE** for the current r2 artifact set. The initially reported F1 is retracted by direct original-PNG pixel evidence below.

**Retracted F1 — viewer display artifact, no source defect:** The initial review mistakenly inferred toolbar clipping from the tool-rendered display for eight tablet/desktop error/empty images. The producer disputed this using unchanged exact hashes. Independent direct PNG decoding (Python standard-library zlib, PNG row-filter reconstruction, RGB pixel inspection; no screenshot modification or regeneration) confirms complete toolbar foreground below y=20 in all eight originals. No foreground pixels occur at y=0..10 in the title/refresh regions. The initial clipping assertion and proposed fixture/layout diagnosis are withdrawn. No source fix is warranted.

Pixel evidence uses inclusive `(x_min,y_min,x_max,y_max)` coordinates and classifies dark-image light foreground as all RGB channels >150, light-image dark foreground as all channels <100. Regions inspected: title x=80..114 / refresh x=670..689 for tablet; title x=196..230 / refresh x=1226..1245 for desktop; y=0..55. The corresponding exact filenames and SHA-256 values are in the frozen image manifest below.

| Images (both error and empty) | Title foreground bounds | Refresh foreground bounds |
|---|---|---|
| tablet_768_dark | (80,22,111,37) | (672,20,687,34) |
| tablet_768_light | (82,23,111,36) | (673,21,686,34) |
| desktop_1440_dark | (196,22,227,37) | (1228,20,1243,34) |
| desktop_1440_light | (198,23,227,36) | (1229,21,1242,34) |

For the two disputed examples specifically, `profiles_tablet_768_dark_empty.png` remains SHA-256 `b8bd01c164a85c2cc0f2008f18079c3cf6695aa2042502080653c42629559de6`, and `profiles_desktop_1440_light_error.png` remains `3e38217f2c9d7987aac2645982a7d02a3ed57688f912b6e4fb64a2e27c526009`. Original-byte evidence takes precedence over the viewer's apparent crop.

**Resolved artifact finding:** First-run `screens/` images showed missing title/action glyphs. The final test's optional `_snapshotTheme` capture branch changes only app-bar and filled/outlined button font families to SnapshotCJK and disables the debug banner. r2 originals resolve those missing glyphs. This was a test-font artifact, not a production-font defect. First-run artifacts remain preserved; remaining superseded originals were not reviewed after coordinator instruction.

## Static and visual evidence

- The test imports and mounts `home: const ProfilePage()` with the actual ProfileCard, YLAsyncState, skeleton and import-sheet code. It does not render `_SnapshotPage` or a replacement page. Provider overrides supply deterministic data and logged-out state; network/persistence success is not claimed.
- The Cartesian product is 3 viewport sizes x 2 brightness values x 4 states = 24 tests and 24 originals. Dimensions are recorded below. Locale is zh-CN; device pixel ratio is 1.
- Retry is tapped and `controller.loads == 1` asserted for each error case. Import is tapped and an actual BottomSheet asserted for each empty case. Diagnostics navigation, successful import, and remote subscription updates are outside this finite assertion set.
- Assertions cover ProfilePage presence, loading skeleton/no cards, error labels, empty text/import label, two real cards and long name, add/update tooltips, and `tester.takeException() == null` before and after actions.
- All 24 final originals were individually inspected once. No card/body overflow, overlapping actions, or unreadable central controls observed. At 360 the long name wraps and ellipsizes intentionally; at 768 it wraps within one column; at 1440 the cards occupy two columns. F1 was disproved by original-byte pixel inspection; no unresolved visual finding remains within this matrix.
- Reused producer evidence: `profiles-screens-r2.log` ends with 24 tests passed; `analyze-r2.log` reports no issues. These are local widget-test/analyzer receipts, not release gates or production deployment/readback.
- No production `lib/` difference from the manifest source base was present at review. Fonts are explicitly substituted for capture; native platform font equivalence, mobile gestures, app-shell integration and whole-estate coverage are not claimed.

## Frozen inputs

Worktree: `/Users/j/Projects/lane-nym/yl-ui-a-profiles`. Observed HEAD: `b8ee79f9e4100fb6130ada94640fbe4785342ab3`. Manifest source base: `b8ee79f9e4100fb6130ada94640fbe4785342ab3`.

| Input | SHA-256 |
|---|---|
| `test/widgets/profiles_real_page_snapshot_test.dart` | `bec7681fe67800d6a6a26393e575c9f0a4c279977c82c85667a60b8234a1ef6d` |
| `lib/modules/profiles/profiles_page.dart` | `ccc581d3a8b001d3e354f18385a0879aa4102f8dafa901b73fe00fccda18b997` |
| `lib/modules/profiles/widgets/profile_card.dart` | `e00ddb7f94552e7ffde1e21eff0ad742941e2258f0888890995af830a84c1c62` |
| `lib/modules/profiles/profiles_import_export.dart` | `977c6c96a68fdf1adc1de874b79e3b0aa35e1ec2f5b167ae757a4ca6f81a5e80` |
| `lib/shared/widgets/yl_scaffold.dart` | `4662381b691cb534e55964bbfce62805ebf29f0ed078565dcef7441268943c13` |
| `lib/theme.dart` | `038fafa3f7033a0c4b86c10d5822c5c63c8105d24bdc96daee1f6b579b7cfb4e` |
| Evidence `screens-manifest.json` | `7c5a0d187d522032208687a5e6e5620cb342c2c97b97b0bc76d35e7a6cfad154` |
| Evidence `profiles-screens-r2.log` | `69dd6eaf726a6ca3f34a97f08979928c8afbeaa5ced43a50746c152af3e9a22a` |
| Evidence `analyze-r2.log` | `914bafa7054d09e745d52ebbf2569dc7089194a7a6a1f101840b3717390031e2` |

## Original-image manifest

Directory: `.claude/state/link-takeover/20261104/ui-a/screens-r2/`. All 24 bytestring hashes verified against producer `screens-manifest.json`.

| Original PNG | Dimensions | SHA-256 |
|---|---|---|
| profiles_desktop_1440_dark_empty.png | 1440x900 | `e6a459a9585c8822ff403c735b5341949cd613b36a2e14952af92ed298077891` |
| profiles_desktop_1440_dark_error.png | 1440x900 | `1d9e03a6a5dc9975c537d46358774dceb0f948f5de3781c2aac47967be430644` |
| profiles_desktop_1440_dark_loading.png | 1440x900 | `c4c1b387a32e9c2d93eb73ef76fb06f9e3d1a4e8d640c342edb9c15a24e27288` |
| profiles_desktop_1440_dark_long_name.png | 1440x900 | `bc5d31d58b849ac1c891a8b764dc3b6640c00c57d83525bcee075f528b550ccb` |
| profiles_desktop_1440_light_empty.png | 1440x900 | `fc9611399bcec62b2462e2a910becc742292e64f0f5a92dd66f1c894c3af9616` |
| profiles_desktop_1440_light_error.png | 1440x900 | `3e38217f2c9d7987aac2645982a7d02a3ed57688f912b6e4fb64a2e27c526009` |
| profiles_desktop_1440_light_loading.png | 1440x900 | `3dff3a9385164cc35737391d5ec6c5a2a6e0a7b873b98ebfc9fd926e5bbea747` |
| profiles_desktop_1440_light_long_name.png | 1440x900 | `d8cd71411371d916e1096f518af0b56fa676279b3b7e8cf74978daf6a825c597` |
| profiles_phone_360_dark_empty.png | 360x800 | `101a1c5ff587b592b353490fea34128272f98e66066252299bf7689ad9aed78f` |
| profiles_phone_360_dark_error.png | 360x800 | `e7bd1277d24c2f350b5209ed49f984d2e7caa19158a35b05fa74ed1e50197556` |
| profiles_phone_360_dark_loading.png | 360x800 | `1319fddcdb0ca7e7c148c360e01ab657df6bc51d97fdb63eaf145f5868ec88bd` |
| profiles_phone_360_dark_long_name.png | 360x800 | `4463d4f1500025d8e30a8814b72d5223eae24d8e142f46bb27f9805de0d992ef` |
| profiles_phone_360_light_empty.png | 360x800 | `c6fc63168384de8c9d46797843511fae447a3bbc235897e96487fd3abd1b1dd2` |
| profiles_phone_360_light_error.png | 360x800 | `dbf15cbc4ce3249e9085c41b6e2050c432938dab5e8c836fb73d8fc958b38214` |
| profiles_phone_360_light_loading.png | 360x800 | `2466e8ffda365d578dc6c8f28f7b26a7b09715bc0c0c57300257090e71016c9f` |
| profiles_phone_360_light_long_name.png | 360x800 | `443ed99ee3bef2a9a70f868188e7aff6ed50bba9a2927f4494d610712acfa134` |
| profiles_tablet_768_dark_empty.png | 768x1024 | `b8bd01c164a85c2cc0f2008f18079c3cf6695aa2042502080653c42629559de6` |
| profiles_tablet_768_dark_error.png | 768x1024 | `853350fdd6a1850625d67719fd789d1b5b515f950eb9f1bef3e866c93ffd0867` |
| profiles_tablet_768_dark_loading.png | 768x1024 | `192c6334c61ed633a3e49cfd23302248209d4359141f39b9946b7bad96494f0b` |
| profiles_tablet_768_dark_long_name.png | 768x1024 | `497f0c7e8d7885b94fdd60e43c35f46910c4aad57cfce9e7c77c62ed6b731190` |
| profiles_tablet_768_light_empty.png | 768x1024 | `4de4867c7b90bd5ec04cc68c76d8af05533868e12c93b0f28331f9f8b07cd6dc` |
| profiles_tablet_768_light_error.png | 768x1024 | `717837b1dfbec9f2d9ee35349261ab38d4f4d53e579d9a4511ed7acf02f37a60` |
| profiles_tablet_768_light_loading.png | 768x1024 | `405f58f43107f08cf79830ab31b9a9416ae3a056d3ea0cf384bcbc36ec13d268` |
| profiles_tablet_768_light_long_name.png | 768x1024 | `e6dd8b82fd27720119c61dd108897f34bed4861293706e7678c46a01b0073ea4` |

Next: coordinator owns acceptance/integration. No further UI-A source repair or screenshot regeneration is requested by this review. Approval covers the local finite matrix only and does not establish production deployment.

## Signed candidate binding

APPROVE binds to signed commit `5fd82f2c0c512ccad5268fdcfe2521fb4a84f6d5`, tree `3eabdf67ca8c17c02134b9d0fe2708f71b32f47a`. Git signature verification succeeded. All six reviewed test/source file SHA-256 values above match the committed bytes exactly; the r2 manifest SHA-256 is unchanged. This is a file-identity binding only: no image re-review, regeneration or test execution was performed. Coordinator-reported native hook result: 5,189 passed and eight pre-existing skips; skipped cases are not counted as passed. The prior finite local acceptance and production-evidence limits remain unchanged.

## Receipt provenance

Review time is the original independent review artifact modification time, including its signed candidate binding. Test time is the original raw command log modification time. The exact original invocation was recovered from the producing session record at 2026-11-04T03:47:20.949Z; it specified neither concurrency nor reporter. The copied log is byte-identical. This test-only change passed the finite 24-case matrix; native hook passed 5,189 cases with eight existing skips excluded from passing counts. No publication is asserted.
