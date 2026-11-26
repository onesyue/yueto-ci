"""Carried documents must not reintroduce removed sing-box or Xray keys."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_core_breakage.py"
RUNNER = ROOT / "scripts" / "run-policy-tests.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CoreBreakageTest(unittest.TestCase):
    def test_carried_documents_exclude_removed_core_keys(self):
        checker = _load(SCRIPT, "check_core_breakage")
        runner = _load(RUNNER, "run_policy_tests")
        self.assertIn("test_core_breakage", runner.discovered_modules(ROOT / "tests"))
        self.assertIn("R2-05 #483", checker.__doc__)
        self.assertEqual(len(checker.UNAMBIGUOUS), len(set(checker.UNAMBIGUOUS)))

        source = Path(__file__).read_text(encoding="utf-8")
        quoted = []
        for key in checker.UNAMBIGUOUS:
            quoted.append(key)
        quoted.extend(checker.SINGBOX_116_DNS_RULE_KEYS)
        quoted.extend(checker.SINGBOX_116_DNS_ADDRESS_FILTER_KEYS)
        quoted.append(checker.SINGBOX_116_TLS_ACME)
        quoted.append(checker.SINGBOX_114_DNS_SERVER_ADDRESS)
        quoted.append(checker.XRAY_26_REMOVED_SECURITY)
        for key in quoted:
            self.assertNotIn(f'"{key}"', source)
            self.assertNotIn(f"'{key}'", source)

        findings, documents = checker.scan_root(ROOT)
        self.assertGreater(documents, 0)
        self.assertEqual(findings, [])
        clean = subprocess.run(
            [sys.executable, str(SCRIPT), str(ROOT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIn("findings=0", clean.stdout)

        address = checker.SINGBOX_114_DNS_SERVER_ADDRESS
        detour = checker.SINGBOX_114_DNS_SERVER_DETOUR
        server_type = checker.SINGBOX_114_DNS_SERVER_TYPE
        strategy = checker.SINGBOX_DNS_STRATEGY
        outbound = checker.SINGBOX_DNS_RULE_OUTBOUND
        acme = checker.SINGBOX_116_TLS_ACME
        tls_parent = checker.SINGBOX_116_TLS_PARENT
        address_filter = checker.SINGBOX_116_DNS_ADDRESS_FILTER_KEYS[0]
        match_response = checker.SINGBOX_116_MATCH_RESPONSE
        network = checker.XRAY_26_NETWORK
        stream = checker.XRAY_26_STREAM_SETTINGS
        removed_transport = checker.XRAY_26_REMOVED_TRANSPORTS[0]
        security = checker.XRAY_26_SECURITY
        removed_security = checker.XRAY_26_REMOVED_SECURITY

        removed = {key: "example.test" for key in checker.UNAMBIGUOUS}
        legacy_server = {
            address: "192.0.2.53",
            strategy: "ipv4_only",
            detour: "direct",
        }
        current_server = {
            server_type: "udp",
            "server": "192.0.2.53",
            detour: "direct",
        }
        inline_acme = {
            "inbounds": [{tls_parent: {acme: {"domain": ["example.com"]}}}],
        }
        provider_acme = {
            "certificate_providers": [{"type": acme}],
        }
        current_route_rule = {"route": {"rules": [{outbound: "direct"}]}}
        current_filter = {
            "dns": {"rules": [{address_filter: ["192.0.2.0/24"], match_response: True}]},
        }
        removed_xray = {
            "outbounds": [
                {stream: {network: removed_transport}},
                {security: removed_security},
            ],
        }
        current_transport = {"outbounds": [{stream: {network: "tcp"}}]}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_root = root / "bad"
            good_root = root / "good"
            bad_root.mkdir()
            good_root.mkdir()
            (bad_root / "removed.json").write_text(
                json.dumps({
                    "inbounds": [removed, inline_acme["inbounds"][0]],
                    "dns": {
                        "servers": [legacy_server],
                        "rules": [{
                            outbound: "direct",
                            strategy: "ipv4_only",
                            address_filter: ["192.0.2.0/24"],
                        }],
                    },
                    "outbounds": removed_xray["outbounds"],
                }),
                encoding="utf-8",
            )
            (good_root / "current.json").write_text(
                json.dumps({
                    "dns": {
                        "servers": [current_server],
                        "rules": current_filter["dns"]["rules"],
                    },
                    "certificate_providers": provider_acme["certificate_providers"],
                    **current_route_rule,
                    "outbounds": current_transport["outbounds"],
                }),
                encoding="utf-8",
            )
            bad, _bad_documents = checker.scan_root(bad_root)
            good, _good_documents = checker.scan_root(good_root)
            cli = subprocess.run(
                [sys.executable, str(SCRIPT), str(bad_root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        catalogs = {item.catalog for item in bad}
        self.assertEqual(catalogs, {
            checker.CATALOG_114,
            checker.CATALOG_116,
            checker.CATALOG_XRAY,
        })
        keys = {item.key for item in bad}
        self.assertTrue(set(checker.UNAMBIGUOUS).issubset(keys))
        self.assertIn(address, keys)
        self.assertIn(detour, keys)
        self.assertIn(acme, keys)
        self.assertIn(outbound, keys)
        self.assertIn(strategy, keys)
        self.assertIn(address_filter, keys)
        self.assertIn(network, keys)
        self.assertIn(security, keys)
        self.assertEqual(good, [])
        self.assertEqual(cli.returncode, 1, cli.stdout)
        self.assertIn(checker.CATALOG_114, cli.stderr)


if __name__ == "__main__":
    unittest.main()
