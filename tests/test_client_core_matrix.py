"""Unit tests for the report-only client core interop matrix."""

from __future__ import annotations

import contextlib
import gzip
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from client_matrix.catalog import (  # noqa: E402
    CLIENTS,
    CLIENTS_BY_ID,
    HOP_PORT_FIRST,
    HOP_PORT_LAST,
    LISTEN_HOST,
    PROTOCOL_HY2_GECKO,
    PROTOCOL_HY2_PORT_HOP,
    PROTOCOL_HY2_SALAMANDER,
    PROTOCOL_REALITY_CLASSICAL,
    PROTOCOL_REALITY_HYBRID,
    PROTOCOL_XHTTP,
    address_commands,
    client_argv,
    hop_commands,
    node_argv,
)
from client_matrix.configs import render_client, render_node  # noqa: E402
from client_matrix.live import FetchError, extract_binary, read_https, verify_digest  # noqa: E402
from client_matrix.material import Material, generate_material, validate_material  # noqa: E402
from client_matrix.runner import (  # noqa: E402
    build_report,
    execute,
    plans,
    redact,
    render_markdown,
    strict_exit,
    write_report,
)
from client_matrix.__main__ import main  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "client-core-matrix.yml"
MATERIAL = Material(
    user_uuid="11111111-1111-4111-8111-111111111111",
    obfs_password="0123456789abcdef0123456789abcdef",
    reality_private_key="A" * 43,
    reality_public_key="B" * 43,
    short_id="0011223344556677",
)
REF = "a" * 40


class CatalogTest(unittest.TestCase):
    def test_pins_and_commands_use_test_net(self) -> None:
        self.assertEqual([pin.client_id for pin in CLIENTS], ["sing-box", "mihomo", "xray", "yue-mihomo"])
        self.assertEqual(len(plans()), 24)
        self.assertTrue(CLIENTS_BY_ID["sing-box"].sha256)
        self.assertEqual(CLIENTS_BY_ID["yue-mihomo"].archive, "source")
        self.assertEqual(client_argv("/bin/sing-box", "sing-box", "c.json"), ("/bin/sing-box", "run", "-c", "c.json"))
        self.assertEqual(client_argv("/bin/mihomo", "mihomo", "c.yaml")[1], "-f")
        self.assertEqual(node_argv("/bin/yue-node", "node.yml"), ("/bin/yue-node", "-c", "node.yml"))
        addresses = " ".join(" ".join(command) for command in address_commands())
        self.assertIn("192.0.2.10/32", addresses)
        self.assertIn("203.0.113.10/32", addresses)
        hop = " ".join(" ".join(command) for command in hop_commands(2445))
        self.assertIn(f"{HOP_PORT_FIRST}-{HOP_PORT_LAST}", hop)
        self.assertIn(LISTEN_HOST, hop)
        self.assertIn(":2445", hop)
        self.assertIn("yueto_matrix", hop)

    def test_generated_material_keeps_key_lengths(self) -> None:
        material = generate_material()
        validate_material(material)
        self.assertEqual(len(material.reality_private_key), 43)
        self.assertEqual(len(material.reality_public_key), 43)
        self.assertEqual(len(material.short_id), 16)


class ConfigTest(unittest.TestCase):
    def test_node_configs_are_standalone_test_net(self) -> None:
        salamander = render_node(PROTOCOL_HY2_SALAMANDER, MATERIAL, "/tmp/matrix-state")
        gecko = render_node(PROTOCOL_HY2_GECKO, MATERIAL, "/tmp/matrix-state")
        hop = render_node(PROTOCOL_HY2_PORT_HOP, MATERIAL, "/tmp/matrix-state")
        reality = render_node(PROTOCOL_REALITY_HYBRID, MATERIAL, "/tmp/matrix-state")
        xhttp = render_node(PROTOCOL_XHTTP, MATERIAL, "/tmp/matrix-state")
        for text in (salamander, gecko, hop, reality, xhttp):
            self.assertNotIn("panel", text)
            self.assertNotIn("splithttp", text)
            self.assertNotIn("yue.to", text)
            self.assertIn('id: "matrix"', text)
            self.assertIn("192.0.2.10", text)
            self.assertIn("example.com", text)
        self.assertIn('obfs: "salamander"', salamander)
        self.assertNotIn("gecko", salamander)
        self.assertIn('obfs: "gecko"', gecko)
        self.assertIn('obfs: "gecko"', hop)
        self.assertIn("server_port: 2443", salamander)
        self.assertIn("server_port: 2444", gecko)
        self.assertIn("server_port: 2445", hop)
        self.assertIn('network: "tcp"', reality)
        self.assertIn("tls: 2", reality)
        self.assertIn('dest: "192.0.2.1:443"', reality)
        self.assertIn('network: "xhttp"', xhttp)
        self.assertIn("tls: 1", xhttp)
        self.assertNotIn("flow:", xhttp)

    def test_clients_keep_key_share_and_unsupported_cells(self) -> None:
        sing_hop, _reason = render_client("sing-box", PROTOCOL_HY2_PORT_HOP, MATERIAL)
        sing_hybrid, _reason = render_client("sing-box", PROTOCOL_REALITY_HYBRID, MATERIAL)
        sing_classical, _reason = render_client("sing-box", PROTOCOL_REALITY_CLASSICAL, MATERIAL)
        sing_xhttp, xhttp_reason = render_client("sing-box", PROTOCOL_XHTTP, MATERIAL)
        self.assertIsNone(sing_xhttp)
        self.assertIn("xhttp", xhttp_reason)
        assert sing_hop is not None and sing_hybrid is not None and sing_classical is not None
        self.assertIn("20000:20007", sing_hop)
        self.assertIn("30s", sing_hop)
        self.assertIn("X25519MLKEM768", sing_hybrid)
        self.assertNotIn("X25519MLKEM768", sing_classical)
        self.assertIn('"X25519"', sing_classical)
        mihomo_hybrid, _reason = render_client("mihomo", PROTOCOL_REALITY_HYBRID, MATERIAL)
        mihomo_classical, _reason = render_client("mihomo", PROTOCOL_REALITY_CLASSICAL, MATERIAL)
        mihomo_hop, _reason = render_client("mihomo", PROTOCOL_HY2_PORT_HOP, MATERIAL)
        assert mihomo_hybrid and mihomo_classical and mihomo_hop
        self.assertIn("support-x25519mlkem768: true", mihomo_hybrid)
        self.assertIn("support-x25519mlkem768: false", mihomo_classical)
        self.assertIn("20000-20007", mihomo_hop)
        self.assertIn("hop-interval: 30", mihomo_hop)
        fork_xhttp, _reason = render_client("yue-mihomo", PROTOCOL_XHTTP, MATERIAL)
        assert fork_xhttp is not None
        self.assertIn("network: \"xhttp\"", fork_xhttp)
        self.assertNotIn("splithttp", fork_xhttp)
        xray_hy2, hy2_reason = render_client("xray", PROTOCOL_HY2_SALAMANDER, MATERIAL)
        xray_hybrid, _reason = render_client("xray", PROTOCOL_REALITY_HYBRID, MATERIAL)
        xray_classical, _reason = render_client("xray", PROTOCOL_REALITY_CLASSICAL, MATERIAL)
        xray_xhttp, _reason = render_client("xray", PROTOCOL_XHTTP, MATERIAL)
        self.assertIsNone(xray_hy2)
        self.assertIn("hy2-salamander", hy2_reason)
        assert xray_hybrid and xray_classical and xray_xhttp
        self.assertIn("hellochrome_155", xray_hybrid)
        self.assertIn("hellochrome_120", xray_classical)
        self.assertNotIn("hellochrome_155", xray_classical)
        self.assertIn('"network": "xhttp"', xray_xhttp)
        self.assertNotIn("splithttp", xray_xhttp)


class ReportTest(unittest.TestCase):
    def test_failures_are_redacted_and_only_strict_mode_fails(self) -> None:
        called: list[tuple[str, str]] = []

        def dial(plan):
            called.append((plan.client_id, plan.protocol))
            return "fail", MATERIAL.user_uuid + " " + MATERIAL.reality_private_key

        results = execute(plans(), dial)
        self.assertEqual(len(results), 24)
        self.assertEqual(sum(item.status == "unsupported" for item in results), 4)
        self.assertEqual(sum(item.status == "fail" for item in results), 20)
        self.assertNotIn(("sing-box", PROTOCOL_XHTTP), called)
        self.assertNotIn(("xray", PROTOCOL_HY2_SALAMANDER), called)
        self.assertNotIn(("xray", PROTOCOL_HY2_GECKO), called)
        self.assertNotIn(("xray", PROTOCOL_HY2_PORT_HOP), called)
        self.assertTrue(all(MATERIAL.user_uuid not in item.detail for item in results))
        self.assertTrue(all(MATERIAL.reality_private_key not in item.detail for item in results))
        self.assertEqual(strict_exit(results), 1)
        unsupported = tuple(plan for plan in plans() if not plan.supported)
        clean = execute(unsupported, lambda _plan: (_ for _ in ()).throw(AssertionError("dialed")))
        self.assertEqual(strict_exit(clean), 0)
        passed = execute(plans(), lambda _plan: ("pass", "ready"))
        self.assertEqual(strict_exit(passed), 0)
        report = build_report(REF, True, results)
        self.assertEqual(report["summary"]["total"], 24)
        markdown = render_markdown(report)
        self.assertIn("Gating is off", markdown)
        self.assertNotIn(MATERIAL.user_uuid, markdown)
        self.assertEqual(redact(MATERIAL.short_id), "[redacted]")

    def test_report_files_round_trip(self) -> None:
        results = execute(plans(), lambda _plan: ("pass", "ready"))
        report = build_report(REF, True, results)
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "matrix"
            write_report(prefix, report)
            self.assertIn(REF, prefix.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertIn("pass=20", prefix.with_suffix(".md").read_text(encoding="utf-8"))


class FetchTest(unittest.TestCase):
    def test_http_and_digest_mismatch_are_rejected(self) -> None:
        with self.assertRaises(FetchError) as caught:
            read_https("http://example.com/client.gz", lambda _url: io.BytesIO(b"x"))
        self.assertIn("https", str(caught.exception))
        with self.assertRaises(FetchError) as mismatch:
            verify_digest("mihomo", "0" * 64, b"not-the-asset")
        self.assertIn("digest mismatch", str(mismatch.exception))
        self.assertNotIn("not-the-asset", str(mismatch.exception))

    def test_gzip_extracts_and_traversal_does_not(self) -> None:
        body = b"#!/bin/sh\necho ok\n"
        with tempfile.TemporaryDirectory() as tmp:
            extracted = extract_binary("gz", "mihomo", gzip.compress(body), Path(tmp))
            self.assertEqual(extracted.read_bytes(), body)
            self.assertTrue(extracted.stat().st_mode & 0o111)
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                payload = b"echo\n"
                info = tarfile.TarInfo("../sing-box")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            with self.assertRaises(FetchError):
                extract_binary("tar.gz", "sing-box", buffer.getvalue(), Path(tmp))
            self.assertFalse((Path(tmp).parent / "sing-box").exists())


class CliTest(unittest.TestCase):
    def test_catalog_and_ref_guards_do_not_download(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["catalog"])
        self.assertEqual(code, 0)
        self.assertIn(CLIENTS_BY_ID["sing-box"].sha256, buffer.getvalue())
        self.assertEqual(
            main(
                [
                    "run",
                    "--report-only",
                    "--yue-node-ref",
                    "not-a-commit",
                    "--node-hy2",
                    "/missing-hy2",
                    "--node-vless",
                    "/missing-vless",
                    "--cache",
                    "/missing-cache",
                    "--output",
                    "/missing-output",
                ]
            ),
            2,
        )
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                main(
                    [
                        "run",
                        "--strict",
                        "--yue-node-ref",
                        REF,
                        "--node-hy2",
                        str(Path(tmp) / "missing-hy2"),
                        "--node-vless",
                        str(Path(tmp) / "missing-vless"),
                        "--cache",
                        tmp,
                        "--output",
                        str(Path(tmp) / "matrix"),
                    ]
                ),
                2,
            )


class WorkflowTest(unittest.TestCase):
    def test_dispatch_job_embeds_pins_and_cannot_publish(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("\non:\n  workflow_dispatch:\n", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertNotIn("ubuntu-latest", workflow)
        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", workflow)
        self.assertIn("repositories: yue-node,mihomo", workflow)
        self.assertIn("cache: false", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertEqual(workflow.count("${{ inputs.yue_node_ref }}"), 1)
        self.assertNotIn("${{ inputs.", workflow.split("run: |", 1)[1])
        self.assertIn("python3 -m client_matrix run", workflow)
        self.assertIn("--report-only", workflow)
        self.assertNotIn("--strict", workflow)
        self.assertIn("ref: ${{ steps.node.outputs.ref }}", workflow)
        for forbidden in ("packages: write", "id-token: write", "build-push-action", "cosign", "promote"):
            self.assertNotIn(forbidden, workflow)
        for pin in CLIENTS:
            self.assertIn(pin.commit, workflow)
            if pin.sha256:
                self.assertIn(pin.sha256, workflow)


if __name__ == "__main__":
    unittest.main()
