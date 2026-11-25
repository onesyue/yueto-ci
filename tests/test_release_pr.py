"""Per-service release pull requests after a verified promote."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_pr", ROOT / "scripts/release_pr.py")
assert SPEC is not None and SPEC.loader is not None
release_pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_pr)

FAKE_RELEASE_YAML = r'''
SCHEMA = "2"
COMPONENTS = (
    "yue-node", "yueboard", "yueops-web", "yue-bot", "checkin-api",
    "ui-console", "ui-miniapp", "ui-site", "ui-board-web",
)

def parse(text):
    import json
    return json.loads(text)

def render(record):
    import json
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"

def signature_input(record):
    return render(record).encode("utf-8")

def validate(record):
    problems = []
    if record.get("schema") != "2":
        problems.append("schema")
    comps = record.get("components") or {}
    if not isinstance(comps, dict) or not comps:
        problems.append("components")
    desired = record.get("desired") or {}
    generation = str(desired.get("generation", ""))
    if not generation.isdigit() or generation == "0":
        problems.append("generation")
    production = desired.get("production") or {}
    if set(production) != set(comps):
        problems.append("coverage")
    for name, body in comps.items():
        if name not in COMPONENTS:
            problems.append(name)
        digest = str((body or {}).get("digest", ""))
        if not digest.startswith("sha256:") or len(digest) != 71:
            problems.append("digest")
    return problems
'''


class FakeYaml:
    SCHEMA = "2"
    COMPONENTS = (
        "yue-node", "yueboard", "yueops-web", "yue-bot", "checkin-api",
        "ui-console", "ui-miniapp", "ui-site", "ui-board-web",
    )

    def parse(self, text):
        return json.loads(text)

    def render(self, record):
        return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"

    def signature_input(self, record):
        return self.render(record).encode("utf-8")

    def validate(self, record):
        problems = []
        if record.get("schema") != self.SCHEMA:
            problems.append("schema")
        comps = record.get("components") or {}
        if not isinstance(comps, dict) or not comps:
            problems.append("components")
        desired = record.get("desired") or {}
        generation = str(desired.get("generation", ""))
        if not generation.isdigit() or generation == "0":
            problems.append("generation")
        production = desired.get("production") or {}
        if set(production) != set(comps):
            problems.append("coverage")
        for name, body in comps.items():
            if name not in self.COMPONENTS:
                problems.append(name)
            digest = str((body or {}).get("digest", ""))
            if not digest.startswith("sha256:") or len(digest) != 71:
                problems.append("digest")
        return problems


def receipt(service="yue-bot", **overrides):
    fields = {
        "service": service,
        "revision": "a" * 40,
        "digest": "sha256:" + ("b" * 64),
        "image": f"{release_pr.REGISTRY}/{service}",
        "architectures": "amd64",
        "run_id": "1001",
        "run_attempt": "1",
        "workflow_sha": "c" * 40,
        "promoted_at": "2026-11-26T00:00:00Z",
    }
    fields.update(overrides)
    return release_pr.build_receipt(fields)


def provenance(body, **certificate):
    cert = {
        "buildSignerURI": release_pr.WORKFLOW_IDENTITY,
        "sourceRepositoryRef": "refs/heads/master",
        "runInvocationURI": (
            f"https://github.com/{release_pr.CI_REPO}/actions/runs/"
            f"{body['run_id']}/attempts/{body['run_attempt']}"
        ),
        "buildSignerDigest": body["workflow_sha"],
    }
    cert.update(certificate)
    return [{
        "verificationResult": {
            "signature": {"certificate": cert},
            "statement": {"subject": [{"digest": {"sha256": body["digest"][7:]}}]},
        },
    }]


class ReleasePrTest(unittest.TestCase):
    def test_auto_merge_is_on_for_every_catalogued_service_except_node_images(self):
        catalog = release_pr.load_catalog()
        self.assertIn("yue-node", release_pr.NODE_IMAGE_SERVICES)
        self.assertTrue(release_pr.NODE_IMAGE_SERVICES <= set(catalog))
        for name, item in catalog.items():
            merged = release_pr.auto_merge(name)
            if name in release_pr.NODE_IMAGE_SERVICES or item.get("group") == "yue-node":
                self.assertFalse(merged)
            else:
                self.assertTrue(merged)
        with self.assertRaises(release_pr.ReleasePrError):
            release_pr.auto_merge("not-a-service")

    def test_identity_matches_the_readme_production_regex(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        line = next(
            item.strip() for item in readme.splitlines() if item.startswith("^https://")
        )
        self.assertRegex(release_pr.WORKFLOW_IDENTITY, line)
        self.assertEqual(
            release_pr.cosign_identity_args(),
            [
                "--certificate-identity", release_pr.WORKFLOW_IDENTITY,
                "--certificate-oidc-issuer", release_pr.OIDC_ISSUER,
            ],
        )

    def test_push_refuses_master_and_force(self):
        body = receipt()
        branch = release_pr.release_branch(body["service"], body["revision"])
        self.assertEqual(branch, "release/yue-bot-" + body["revision"][:12])
        args = release_pr.git_push_args(branch)
        self.assertEqual(args, ["git", "push", "origin", f"HEAD:refs/heads/{branch}"])
        self.assertNotIn("--force", args)
        self.assertNotIn("-f", args)
        self.assertNotIn("--force-with-lease", args)
        for refused in ("master", "refs/heads/master"):
            with self.subTest(branch=refused):
                with self.assertRaises(release_pr.ReleasePrError):
                    release_pr.git_push_args(refused)
        command = release_pr.git_push_command(Path("."), branch)
        self.assertNotIn("--force", command)
        self.assertNotIn("@", " ".join(command))
        merge = release_pr.pr_merge_args("42")
        self.assertIn("--auto", merge)
        self.assertIn("--squash", merge)
        self.assertNotIn("--admin", merge)

    def test_receipt_rejects_bad_digest_and_architecture(self):
        with self.assertRaises(release_pr.ReleasePrError):
            receipt(digest="sha256:abcd")
        with self.assertRaises(release_pr.ReleasePrError):
            receipt(architectures="amd64,ppc64")
        with self.assertRaises(release_pr.ReleasePrError):
            receipt(image=f"{release_pr.REGISTRY}/other")
        accepted = receipt(architectures="arm64,amd64")
        self.assertEqual(accepted["architectures"], "arm64,amd64")

    def test_generation_bumps_and_same_revision_is_idempotent(self):
        fake = FakeYaml()
        first = release_pr.apply_promotion(fake, None, receipt())
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(json.loads(first)["desired"]["generation"], "1")
        changed = receipt(digest="sha256:" + ("d" * 64))
        second = release_pr.apply_promotion(fake, first, changed)
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(json.loads(second)["desired"]["generation"], "2")
        self.assertIsNone(release_pr.apply_promotion(
            fake, second, receipt(digest="sha256:" + ("d" * 64), promoted_at="2026-11-26T01:00:00Z"),
        ))

    def test_validation_failure_aborts_before_render(self):
        class Rejecting(FakeYaml):
            def validate(self, record):
                return ["digest"]

            def render(self, record):
                raise AssertionError("rendered an invalid record")

        with self.assertRaises(release_pr.ReleasePrError):
            release_pr.apply_promotion(Rejecting(), None, receipt())

    def test_signature_input_must_match_render(self):
        fake = FakeYaml()
        fake.signature_input = lambda record: b"nope"
        with self.assertRaises(release_pr.ReleasePrError):
            release_pr.apply_promotion(fake, None, receipt())

    def test_provenance_binds_the_receipt(self):
        body = receipt()
        release_pr.check_provenance(provenance(body), body)
        with self.assertRaises(release_pr.ReleasePrError):
            release_pr.check_provenance(provenance(body, buildSignerDigest="d" * 40), body)
        with self.assertRaises(release_pr.ReleasePrError):
            wrong = provenance(body)
            wrong[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = "e" * 64
            release_pr.check_provenance(wrong, body)

    def test_cli_render_round_trip_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "scripts" / "release_yaml"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text(FAKE_RELEASE_YAML, encoding="utf-8")
            body = receipt()
            receipt_path = root / "promoted.json"
            receipt_path.write_text(json.dumps(body) + "\n", encoding="utf-8")
            output = root / "github.out"
            script = ROOT / "scripts/release_pr.py"
            first = subprocess.run(
                [sys.executable, str(script), "render", "--receipt", str(receipt_path),
                 "--yueto-root", str(root), "--github-output", str(output)],
                check=False, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "status=rendered\n")
            record = root / "release" / "yue-bot.yaml"
            self.assertTrue(record.is_file())
            self.assertFalse((root / "release.yaml").exists())
            written = record.read_bytes()
            second = subprocess.run(
                [sys.executable, str(script), "render", "--receipt", str(receipt_path),
                 "--yueto-root", str(root), "--github-output", str(output)],
                check=False, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "status=rendered\nstatus=unchanged\n")
            self.assertEqual(record.read_bytes(), written)

    def test_cli_rejects_a_bad_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "promoted.json"
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/release_pr.py"), "record-promoted",
                    "--service", "yue-bot",
                    "--revision", "a" * 40,
                    "--digest", "sha256:abcd",
                    "--image", f"{release_pr.REGISTRY}/yue-bot",
                    "--architectures", "amd64",
                    "--run-id", "1001",
                    "--run-attempt", "1",
                    "--workflow-sha", "c" * 40,
                    "--promoted-at", "2026-11-26T00:00:00Z",
                    "--output", str(destination),
                ],
                check=False, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("digest", result.stderr)
            self.assertFalse(destination.exists())

    def test_commit_stages_only_the_record_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "writer@example.test"],
                check=True, timeout=30,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "writer"],
                check=True, timeout=30,
            )
            (root / "README").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README"], check=True, timeout=30)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "seed"],
                check=True, timeout=30,
            )
            hooks = root / "hooks"
            hooks.mkdir()
            hook = hooks / "pre-commit"
            hook.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
            hook.chmod(0o755)
            subprocess.run(
                ["git", "-C", str(root), "config", "core.hooksPath", str(hooks)],
                check=True, timeout=30,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "commit.gpgsign", "true"],
                check=True, timeout=30,
            )
            (root / "other.txt").write_text("leave me\n", encoding="utf-8")
            release = root / "release"
            release.mkdir()
            (release / "yue-bot.yaml").write_text("record\n", encoding="utf-8")
            (release / "yue-bot.yaml.bundle").write_text("bundle\n", encoding="utf-8")
            release_pr.commit_release(root, "yue-bot", "release yue-bot " + ("a" * 12))
            shown = subprocess.run(
                ["git", "-C", str(root), "show", "--name-only", "--format=", "HEAD"],
                check=True, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(
                set(shown.stdout.split()),
                {"release/yue-bot.yaml", "release/yue-bot.yaml.bundle"},
            )
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                check=True, capture_output=True, text=True, timeout=30,
            )
            self.assertIn("other.txt", status.stdout)
            self.assertNotIn("release/yue-bot.yaml", status.stdout)

    def test_open_pushes_without_force_and_auto_merges(self):
        self.assert_open("yue-bot", expect_merge=True)

    def test_node_image_opens_without_auto_merge(self):
        self.assert_open("yue-node", expect_merge=False)

    def assert_open(self, service, expect_merge):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.seed_ledger(Path(tmp), service)
            calls = []
            original = release_pr._run

            def runner(args, check=True, capture=False, text=False):
                if args[0] == "gh":
                    calls.append(args)
                    if args[1:3] == ["pr", "list"]:
                        return subprocess.CompletedProcess(args, 0, "[]\n", "")
                    if args[1:3] == ["pr", "create"]:
                        url = f"https://github.com/{release_pr.YUETO_REPO}/pull/42\n"
                        return subprocess.CompletedProcess(args, 0, url, "")
                    if args[1:3] == ["pr", "merge"]:
                        return subprocess.CompletedProcess(args, 0, "", "")
                    raise AssertionError(args)
                if "ls-remote" in args:
                    calls.append(args)
                    return subprocess.CompletedProcess(args, 2, "", "")
                if args[0] == "git" and "push" in args:
                    calls.append(args)
                    self.assertNotIn("--force", args)
                    self.assertNotIn("-f", args)
                    return subprocess.CompletedProcess(args, 0, "", "")
                return original(args, check=check, capture=capture, text=text)

            release_pr._run = runner
            try:
                url = release_pr.open_release(root, receipt(service))
            finally:
                release_pr._run = original
                sys.modules.pop("release_yaml", None)
            self.assertTrue(url.endswith("/42"))
            pushed = [item for item in calls if "push" in item]
            self.assertEqual(len(pushed), 1)
            self.assertNotIn("--force", pushed[0])
            merged = [item for item in calls if len(item) > 2 and item[1:3] == ["pr", "merge"]]
            self.assertEqual(bool(merged), expect_merge)
            if expect_merge:
                self.assertIn("--auto", merged[0])
                self.assertNotIn("--admin", merged[0])

    def test_existing_branch_with_different_bytes_is_not_pushed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.seed_ledger(Path(tmp), "yue-bot")
            original = release_pr._run
            pushed = []

            def runner(args, check=True, capture=False, text=False):
                if args[0] == "gh" and args[1:3] == ["pr", "list"]:
                    return subprocess.CompletedProcess(args, 0, "[]\n", "")
                if "ls-remote" in args:
                    return subprocess.CompletedProcess(args, 0, "matched\n", "")
                if "fetch" in args:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if "show" in args:
                    return subprocess.CompletedProcess(args, 0, b"different", b"")
                if args[0] == "git" and "push" in args:
                    pushed.append(args)
                    return subprocess.CompletedProcess(args, 0, "", "")
                return original(args, check=check, capture=capture, text=text)

            release_pr._run = runner
            try:
                with self.assertRaises(release_pr.ReleasePrError):
                    release_pr.open_release(root, receipt())
            finally:
                release_pr._run = original
                sys.modules.pop("release_yaml", None)
            self.assertEqual(pushed, [])

    def test_supply_chain_script_retries_provenance_and_signs_with_keyless_identity(self):
        verify = (ROOT / "scripts/verify-promoted-supply-chain.sh").read_text(encoding="utf-8")
        sign = (ROOT / "scripts/sign-release-blob.sh").read_text(encoding="utf-8")
        self.assertIn("for attempt in 1 2 3 4", verify)
        self.assertIn("sleep 15", verify)
        self.assertIn("verify-sbom-attestations.py", verify)
        self.assertIn("check-provenance", verify)
        self.assertNotIn("--force", verify)
        self.assertIn("keyless_cosign sign-blob", sign)
        self.assertIn("verify-blob", sign)
        self.assertNotIn("gpg", sign)
        self.assertNotIn("--force", sign)
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn("python3 .ci-policy/scripts/release_pr.py record-promoted", workflow)
        self.assertIn("\n  release-pr:\n", workflow)
        self.assertNotRegex(workflow, r"\bgit\s+push\b")
        self.assertNotRegex(workflow, r"release\.yaml")

    def seed_ledger(self, root, service):
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=30)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "writer@example.test"],
            check=True, timeout=30,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "writer"],
            check=True, timeout=30,
        )
        (root / "README").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README"], check=True, timeout=30)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True, timeout=30)
        remote = sorted(release_pr.ALLOWED_REMOTES)[0]
        subprocess.run(
            ["git", "-C", str(root), "remote", "add", "origin", remote],
            check=True, timeout=30,
        )
        package = root / "scripts" / "release_yaml"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(FAKE_RELEASE_YAML, encoding="utf-8")
        body = receipt(service)
        output = root / "github.out"
        release_pr.render_release(root, body, str(output))
        bundle = root / "release" / f"{service}.yaml.bundle"
        bundle.write_bytes(b"bundle\n")
        return root


if __name__ == "__main__":
    unittest.main()
