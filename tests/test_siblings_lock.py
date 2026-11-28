"""Sibling checkouts use ci/siblings.lock, never a branch name."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCK = ROOT / "ci" / "siblings.lock"
SPEC = importlib.util.spec_from_file_location(
    "update_siblings_lock", ROOT / "scripts" / "update-siblings-lock.py"
)
assert SPEC is not None and SPEC.loader is not None
PIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PIN)

DYNAMIC_REFS = {
    "${{ matrix.ref }}",
    "${{ steps.plan.outputs.ops_source }}",
    "${{ needs.plan.outputs.ops_source }}",
    "${{ needs.plan.outputs.yueboard_contract_ref }}",
    # Ops tests run the Board the sealed admission names (test_board_from_signed_plan).
    "${{ steps.board.outputs.board }}",
    "${{ github.event.inputs.ref }}",
    "${{ github.sha }}",
    "${{ steps.source.outputs.revision }}",
    # client-core-matrix validates this output is a 40-character revision before checkout.
    "${{ steps.node.outputs.ref }}",
    # daily head scan resolves refs/heads/master to a full SHA, then checks that SHA out.
    "${{ steps.heads.outputs.yueops }}",
    "${{ steps.heads.outputs.yueboard }}",
    "${{ steps.heads.outputs.yue_node }}",
}
LITERAL_SHA_REPOS = {"hysteria", "mihomo", "quic-go"}
RESOLVE_COMMAND = {
    "alert-chain-deadman.yml": (
        "python3 .ci-receiver/scripts/update-siblings-lock.py "
        "--github-output --lock .ci-receiver/ci/siblings.lock"
    ),
    "build.yml": (
        '"${YUE_CI_PYTHON:?}" .ci-policy/scripts/update-siblings-lock.py '
        "--github-output --lock .ci-policy/ci/siblings.lock"
    ),
    "weekly-vuln-sbom.yml": (
        "python3 .ci-policy/scripts/update-siblings-lock.py "
        "--github-output --lock .ci-policy/ci/siblings.lock"
    ),
}
SHA_RE = __import__("re").compile(r"[0-9a-f]{40}")


def _uncomment(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _lock_ref(repo: str) -> str:
    return "${{ steps.siblings.outputs." + PIN.output_key(repo) + " }}"


class SiblingLockTest(unittest.TestCase):
    def test_committed_lock_matches_the_generator(self) -> None:
        pins = PIN.load_lock(LOCK)
        self.assertEqual(LOCK.read_text(encoding="utf-8"), PIN.render(pins))
        self.assertEqual(tuple(pins), PIN.REPOS)
        rendered = PIN.github_output(pins)
        for repo, sha in pins.items():
            self.assertIn(f"{PIN.output_key(repo)}={sha}\n", rendered)

    def test_resolve_reads_the_lock_and_does_not_spawn(self) -> None:
        pins = PIN.load_lock(LOCK)
        with mock.patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertEqual(
                PIN.main(["--resolve", "onesyue/yueto", "--lock", str(LOCK)]),
                0,
            )
        with mock.patch("sys.stdout") as stdout, mock.patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertEqual(PIN.main(["--resolve", "yueto", "--lock", str(LOCK)]), 0)
            self.assertEqual(stdout.write.call_args.args[0], pins["yueto"] + "\n")

    def test_github_output_lists_every_sibling(self) -> None:
        pins = PIN.load_lock(LOCK)
        with mock.patch("sys.stdout") as stdout, mock.patch("subprocess.run", side_effect=AssertionError("network")):
            self.assertEqual(PIN.main(["--github-output", "--lock", str(LOCK)]), 0)
        self.assertEqual(stdout.write.call_args.args[0], PIN.github_output(pins))

    def test_write_uses_only_git_ls_remote(self) -> None:
        source = (ROOT / "scripts" / "update-siblings-lock.py").read_text(encoding="utf-8")
        self.assertNotIn("api.github.com", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("gh ", source)
        for repo in PIN.REPOS:
            argv = PIN.remote_argv(repo)
            self.assertEqual(
                argv,
                ["git", "ls-remote", f"https://github.com/onesyue/{repo}.git", PIN.REF],
            )

        pins = {repo: format(index, "040x") for index, repo in enumerate(PIN.REPOS)}
        seen: list[list[str]] = []

        def fake_run(argv, **_kwargs):
            seen.append(list(argv))
            repo = argv[2].removeprefix("https://github.com/onesyue/").removesuffix(".git")
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{pins[repo]}\t{PIN.REF}\n", stderr=""
            )

        with tempfile_lock() as path, mock.patch("subprocess.run", fake_run):
            self.assertEqual(PIN.main(["--write", "--lock", str(path)]), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), PIN.render(pins))
        self.assertEqual(seen, [PIN.remote_argv(repo) for repo in PIN.REPOS])

    def test_write_rejects_a_moved_or_empty_advertisement(self) -> None:
        destination = LOCK.with_name("siblings.lock.reject")
        self.addCleanup(destination.unlink, missing_ok=True)
        destination.write_text("keep\n", encoding="utf-8")

        def fake_run(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", fake_run):
            with self.assertRaises(RuntimeError):
                PIN.main(["--write", "--lock", str(destination)])
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep\n")

    def test_lock_parser_rejects_drift(self) -> None:
        with self.assertRaises(ValueError):
            PIN.load_lock(ROOT / "README.md")
        text = PIN.render(PIN.load_lock(LOCK))
        broken = text.replace(PIN.REPOS[0], "not-a-sibling", 1)
        path = LOCK.with_name("siblings.lock.broken")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(broken, encoding="utf-8")
        with self.assertRaises(ValueError):
            PIN.load_lock(path)


class SiblingCheckoutTest(unittest.TestCase):
    def test_no_workflow_checks_out_a_sibling_branch(self) -> None:
        lock_refs = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            code = _uncomment(text)
            self.assertNotIn("ref: master", code, path.name)
            document = yaml.safe_load(text)
            for job in document["jobs"].values():
                steps = job.get("steps") or []
                resolve = next((step for step in steps if step.get("id") == "siblings"), None)
                used = False
                for step in steps:
                    uses = str(step.get("uses") or "")
                    if not uses.startswith("actions/checkout@"):
                        continue
                    checkout = step.get("with") or {}
                    repository = checkout.get("repository")
                    ref = checkout.get("ref")
                    if repository is None:
                        self.assertIn(ref, (None, "${{ github.sha }}"))
                        continue
                    if repository == "${{ matrix.repo }}":
                        self.assertEqual(ref, "${{ matrix.ref }}")
                        continue
                    if repository == "${{ inputs.repository || github.repository }}":
                        self.assertEqual(ref, "${{ inputs.revision || github.sha }}")
                        continue
                    self.assertIsInstance(repository, str)
                    self.assertTrue(str(repository).startswith("onesyue/"), repository)
                    repo = repository.split("/", 1)[1]
                    if repo in PIN.REPOS and ref == _lock_ref(repo):
                        used = True
                        lock_refs += 1
                        continue
                    if repo in PIN.REPOS and ref in DYNAMIC_REFS:
                        continue
                    if repo == "yueto-ci":
                        self.assertEqual(ref, "${{ github.sha }}")
                        continue
                    if repo in LITERAL_SHA_REPOS:
                        self.assertRegex(ref, SHA_RE)
                        continue
                    self.fail(f"{path.name} checkout of {repository} ref {ref!r} is not pinned")
                if used:
                    self.assertIsNotNone(resolve, path.name)
                    command = RESOLVE_COMMAND[path.name]
                    self.assertIn(command, resolve["run"])
                    self.assertNotIn("ls-remote", resolve["run"])
                    self.assertNotIn("master", resolve["run"])
                elif resolve is not None:
                    self.fail(f"{path.name} resolves a sibling lock it does not checkout")
        self.assertEqual(lock_refs, 10)

    def test_resolve_output_keys_match_the_constant(self) -> None:
        self.assertEqual(
            [PIN.output_key(repo) for repo in PIN.REPOS],
            ["yue_node", "yueboard", "yuelink", "yuelink_ci", "yueops", "yueto"],
        )


class tempfile_lock:
    def __enter__(self):
        self.path = LOCK.with_name("siblings.lock.write-test")
        return self.path

    def __exit__(self, *_exc):
        self.path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
