# yuelink PR65 final exact-head evidence

Current head `fd6cd05998ece2f244955db005adf68291aa95fb`. Current copied log is byte-identical to `.claude/state/c1-c2-consumer/20261104/run1/linux.log`. Prior candidate logs and reviews remain in predecessor commits; the current receipt binds only this head.

Actual Board render outputs pass both locale transformations, pinned core parsing and218 route cases per locale. Subscription/node bootstrap and actual core HTTP DNS flush with a fresh UDP answer preserve the tracked TCP connection. Host/Linux harness required cases have zero skips; native5207 pass excludes8 existing skips. Providers are offline seeds, and automatic fixed-IP DNS discovery or Dart orchestration is not claimed.

Independent review:

```json
{
  "verdict": "APPROVE_SOURCE",
  "reviewer": "root/link independent reviewer",
  "reviewed_at": "2026-11-04T05:29:50.298093+00:00",
  "base": "041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8",
  "files": {
    "core/subscription_dns_refresh_consumer_test.go": "00c0a4fc85bbe62a2c54e26db4c0c58e84bbc707de25968b36c0b8c49b1a4f2e",
    "core/subscription_rendered_corpus_test.go": "7c5e3f88d58248be4a50c815f1cb2163dddaee1b1ca53495e74ed0e277998cb0",
    "core/testdata/rendered_corpus/README.md": "c4620321778e183a7d324c568018db2657529a975275b57d38972fe61e43d3b9",
    "core/testdata/rendered_corpus/clashmeta.en.yaml": "0f7d6e3c0f05cc7f0da885f9854caa7b299f2c83727c0004499975a8dde0fb8d",
    "core/testdata/rendered_corpus/clashmeta.zh-CN.yaml": "4eaca9a3b534696eab7fec6ebbdb5437a6b58bfdaa53c08d68ecdffa81d83fa7",
    "core/testdata/rendered_corpus/render-manifest.json": "a34f7550ee17cd999a6cca1fd926a89419a8b3f03da17ab22828bf33bc0234bf",
    "core/testdata/rendered_corpus/singbox.en.json": "8dcc1e5aab5a7fffb334342915fb0ef7548d7fcd97522b77d3a798fa77b22148",
    "core/testdata/rendered_corpus/singbox.zh-CN.json": "7919119917da485f3b6bb35e2c3eb29a1986faab0e3146c5a10e45b6aee42e15",
    "scripts/test-rendered-corpus.sh": "5a3958bf5fca6d5de1728854a946bd22fa435c6798eaaa2e20f8ad9282b2c2e3",
    "test/core/kernel/config/rendered_template_corpus_test.dart": "991e6f5874787cf318e401b72d1249c88a34b756e7b11c3a2271fbb3f3e045d1",
    "core/subscription_bootstrap_dns_test.go": "47327c087b367487112c6f06a9e388e051b298d2eff3785b53086c1213caba5c",
    "core/subscription_routing_matrix_test.go": "e53b444570e10003184a598972084bf9e35118b2cdc9f3a57bbcfbbc9c702605",
    "test/core/kernel/config/client_honours_server_template_matrix_test.dart": "c07a9d7cd099b3f408bdc123fce7435c640463c31c8e1cd6c2ec99c02787e867"
  },
  "findings": [],
  "checks": [
    "All13 frozen hashes match working bytes. Four render artifacts and full manifest are byte-identical to Board a751 exported artifacts. No production or nested core source changes.",
    "Harness sets actual corpus input, requires absolute effective output and pinned sing-box1.14.3, executes both real ConfigTemplate locale cases and exports their outputs. Rendered nodes are not substituted. Existing synthetic-node helper remains only for legacy absent-node input.",
    "Server rules must remain an ordered subsequence; broad added rules and redirects of matrix destinations fail. AI group membership/type is preserved. English core expected targets are translated explicitly, not inferred from actual results. Both effective locale outputs feed the existing218-case pinned-mihomo matcher matrix.",
    "Full config.Parse handles both effective Meta outputs; sing-box check handles both original rendered JSONs. This is parser and offline-seed evidence, not live datapath/provider acceptance. Missing provider seeds are explicitly logged as empty.",
    "Subscription DNS helper preserves actual service matchers/filter entries while replacing transport endpoints with bounded loopback fixtures. Policy deletion fails resolution and filter deletion restores fake-IP, with actual UDP lookup plus useful HTTP body and original host retained.",
    "Node bootstrap verifies ordinary DNS refusal, then separate ProxyResolver success and actual bootstrap-host plus node-host query observations. Loopback upstream substitution is explicit; no live upstream availability is claimed.",
    "DNS companion calls actual core /dns/query and /cache/dns/flush HTTP endpoints over owned Unix socket. TTL300 cached old answer and exact one-query control precede flush; bounded readback requires new answer and second upstream UDP query. The same registered TCP tracker exchanges bytes before and after. A204 alone is not accepted.",
    "DNS companion covers explicit core cache flush only, not automatic fixed-IP DNS-change detection, interface discovery, or Dart orchestration. Existing streams are actually tracked by the core statistics manager; no whole deployed-core lifecycle claim is inferred."
  ],
  "verification_reused": {
    "host": "Writer host harness4 Dart cases/zero required skip,218 matrix cases per locale, both sing-box1.14.3 checks, core module PASS",
    "linux": "Writer verification.json records complete offline Linux harness PASS,4 Dart/218 matrix each locale/zero required skips, effective output hashes identical host/Linux.",
    "signed_head": "Pending writer signature binding"
  },
  "tests_rerun": false,
  "limits": [
    "Frozen test/fixture/harness source approval only. Linux completion and native signed-hook gate remain required.",
    "Provider freshness, live service-IP routes and automatic Dart DNS-change detection are outside the finite proof."
  ],
  "signed_head": "fd6cd05998ece2f244955db005adf68291aa95fb",
  "signature": "G",
  "bound_at": "2026-11-04T05:49:47.085700+00:00",
  "binding": "All13 committed hashes match previously reviewed source, with only these paths changed. Existing Linux complete harness PASS/no required skips and native5207pass8existing skips reused; no retest. First164 remainsbb."
}
```

Current verification receipt:

```json
{
  "owner": "external thread01a1a4a7",
  "parent": "041c66eaa8e07d1c09a9311e2ada3b8e70bdcdd8",
  "producer": "a751ea8a652a2cef888b2416f4a7f8e617eab7e2",
  "host_harness": {
    "log": "harness-host-r2.log",
    "dart_pass": 4,
    "required_skips": 0,
    "matrix_per_locale": 218,
    "locales": [
      "zh-CN",
      "en"
    ],
    "singbox": "1.14.3 check, both locales"
  },
  "host_core_module": {
    "log": "core-module-host.log",
    "result": "PASS"
  },
  "static": {
    "dart": "dart-analyze.log, PASS",
    "gopls": "gopls.log, CLI PASS; MCP workspace unsupported",
    "shell": "bash -n and shellcheck PASS"
  },
  "linux": {
    "result": "PASS",
    "log": "linux.log",
    "dart_pass": 4,
    "required_skips": 0,
    "matrix_per_locale": 218,
    "image": "sha256:cf320c534782414c6e047c7d79b7c3a1f31433c5e4774c5889d43df525030e48",
    "network": "none",
    "cpus": 2,
    "memory": "4GiB",
    "timezone": "UTC",
    "go": "1.27.3",
    "flutter": "3.47.8",
    "singbox": "1.14.3"
  },
  "review": "APPROVE_SOURCE: .claude/state/link-takeover/20261104/1039/c1-c2-consumer-source-review.json; 13 hashes matched",
  "claim_limits": [
    "Offline seeded providers only; no online service-IP evidence.",
    "DNS companion is actual core HTTP flush/query plus tracked TCP; not automatic Dart DNS-change detection.",
    "No production behavior, nested source or release inputs changed."
  ],
  "scratch": {
    "short_socket_directory": "os.MkdirTemp runtime path recorded in DNS log; removed on return due to Unix sun_path limit",
    "source_snapshot": "linux-source retained for exact independent verification",
    "singbox_linux": "Verified installed cached archive extracted here; retained for reproducibility"
  },
  "effective_outputs": {
    "zh-CN": {
      "host": "0b30f59fbaa316ee6dc888ea28001a20b7393169145f73171854c1700c730c00",
      "linux": "0b30f59fbaa316ee6dc888ea28001a20b7393169145f73171854c1700c730c00"
    },
    "en": {
      "host": "41bd66940f1ba4f6bf8abb0a6494ab82b81fe326f7f086820f74bdfa5f3483a9",
      "linux": "41bd66940f1ba4f6bf8abb0a6494ab82b81fe326f7f086820f74bdfa5f3483a9"
    }
  },
  "native_hook": {
    "result": "PASS",
    "log": "commit.log",
    "passes": 5207,
    "existing_skips": 8
  },
  "commit": "fd6cd05998ece2f244955db005adf68291aa95fb"
}
```
