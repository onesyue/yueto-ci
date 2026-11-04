# yuelink PR63 exact-source evidence

Head `bb034c504e01eecd9777f992edd892958787927f`. Original command-output log: `.claude/state/cn01-joint/20261104/run1/module-linux.log`. The copied log retains original bytes. Independent source review and supplemental evidence follow. They do not imply publication or production acceptance.

```json
{
  "reviewer": "/root/link",
  "reviewed_at": "2026-11-04T04:09:11.544243+00:00",
  "verdict": "APPROVE",
  "scope": "Frozen three-file source delta only, base5fd82f2c; host/Linux suite gate and exact signed successor binding remain writer responsibilities. UI-A parent not re-reviewed.",
  "files": {
    "lib/core/transport/edge_pool_bootstrap.dart": "9db56d8c4398b98894ff8e926225a01b35f3621d939a833007021135f5cae5fe",
    "lib/infrastructure/transport/resolved_connection.dart": "40946f99f61fa2c9f697558526bd72555af4a3d97f53f38eff4ea165319e3a56",
    "test/infrastructure/transport/cn01_joint_dns_consumer_test.dart": "b8c9b206a44dd25aaba4a071791b827386acf9078b5c8b5fd49076c0f9da98db"
  },
  "findings": [],
  "checks": [
    "Null testHostLookup continues to call InternetAddress.lookup; optional lookup is used only in the existing deadline-aware host lookup path. Literal-address and no-deadline behavior, trusted shouldResolve host predicate, proxy handling and TLS hostname validation are unchanged.",
    "Both login and cached refresh exercise real PanelApi and local TLS; trusted DoH survivor bypasses failed/poisoned OS resolver. Stalled provider requests are canceled.",
    "All DoH plus OS failure asserts no business submission and zero dials; mismatched trusted-CA hostname asserts no credentials/bearer received.",
    "Signed expired/rollback rosters cannot replace accepted entry or advance watermark; business request remains exact original host.",
    "Caller timeout test releases delayed OS answer after failure, proves no late dial/fallback/submission and resets testing globals on teardown.",
    "Fourteen new joint cases do not include IPv6 blackhole; existing cn01_transport_final_test.dart:243 covers real TLS login with blackholed IPv6 and cancellation, to be reused under writer complete-suite evidence. No claim that fourteen cases alone establish the entire corpus."
  ],
  "head": "bb034c504e01eecd9777f992edd892958787927f",
  "tree": "9ec22d8774b331364533c6e8f12ed6f85a338d5a",
  "bound_at": "2026-11-04T04:27:57.015079+00:00",
  "binding": "Previously approved three exact file hashes match final signed commit; no source re-review or tests rerun. Writer reports host344/Linux344 no skips and full hook5203 pass8 existing skips."
}
```

Original supplemental artifact: `.claude/state/cn01-joint/20261104/run1/verification.json`

```json
{
  "base": "5fd82f2c0c512ccad5268fdcfe2521fb4a84f6d5",
  "host": {
    "joint": {
      "exit": 0,
      "passed": 14,
      "skips": 0,
      "log": "joint-host.log"
    },
    "module": {
      "exit": 0,
      "passed": 344,
      "skips": 0,
      "log": "module-host.log"
    }
  },
  "analysis": {
    "pinned_sdk": "Flutter3.47.8/Dart3.13.7",
    "exit": 0,
    "log": "analyze.log",
    "mcp": "no errors; applyFixes=false"
  },
  "format": "three explicit paths, unchanged, exit0",
  "linux": {
    "exit": 0,
    "passed": 344,
    "skips": 0,
    "log": "module-linux.log",
    "image": "sha256:cf320c534782414c6e047c7d79b7c3a1f31433c5e4774c5889d43df525030e48",
    "platform": "linux/amd64",
    "timezone": "UTC",
    "sdk": "Flutter3.47.8/Dart3.13.7",
    "concurrency": 1
  },
  "review": "coordinator assigning independent reviewer",
  "source": "source-hashes.json",
  "native_hook": {
    "exit": 0,
    "passed": 5203,
    "existing_skips_not_passed": 8,
    "log": "commit-r2.log",
    "analyzer": "pass",
    "format": "pass",
    "architecture": "pass",
    "security": "pass"
  },
  "native_hook_first": {
    "exit": 1,
    "passed": 5199,
    "skips": 8,
    "failures": 4,
    "log": "commit.log",
    "cause": "New worktree lacked pinned core/mihomo/governance inputs; no source failure",
    "repair": "Detached owned nested worktree materialized from existing object6d60af5d01c4a21aadba9bd4fb2d431242324b8d",
    "setup_log": "submodule-setup.log",
    "targeted_recheck": {
      "exit": 0,
      "passed": 7,
      "log": "submodule-check.log"
    }
  },
  "candidate": {
    "head": "bb034c504e01eecd9777f992edd892958787927f",
    "tree": "9ec22d8774b331364533c6e8f12ed6f85a338d5a",
    "signature": "G",
    "worktree": "clean",
    "source_review": "/Users/j/Projects/yueto/.claude/state/link-takeover/20261104/1039/cn01-joint-source-review.json",
    "reviewed_blob_hashes": "3/3 match signed HEAD",
    "review_binding": "review-binding.json"
  },
  "delivery": {
    "pr": "https://github.com/onesyue/yuelink/pull/63",
    "draft": true,
    "base": "cx/ui-a-profiles",
    "branch": "codex/cn01-joint-20261104",
    "remote_head": "bb034c504e01eecd9777f992edd892958787927f",
    "push_exit": 0,
    "worktree": "clean",
    "published": false,
    "source_custody": "frozen and returned to coordinator",
    "jobs": "none",
    "locks": "none"
  }
}

```

All344 affected host and Linux cases passed without skips. The5203 native-hook pass count excludes8 existing skips. The first missing-submodule setup failure remains retained and was corrected before the successful complete native hook.
