"""Execute the workflow bootstrap with controlled external commands and files.

The fixtures model APT trust/fetch failures, not cryptography or a real install.
Only four literal machine paths are relocated; the workflow shell is unchanged.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
STEP = "      - name: Install native YueOps PostgreSQL 18 test toolchain\n"
FINGERPRINT = "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"


def workflow_shell():
    workflow = (ROOT / ".github/workflows/build.yml").read_text()
    assert workflow.count(STEP) == 1
    step = workflow.split(STEP, 1)[1].split("\n      - name:", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


COMMAND_FIXTURE = r'''
import json, os, pathlib, stat, sys

root = pathlib.Path(os.environ["FIXTURE_ROOT"])
command = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
fault = os.environ.get("FIXTURE_FAULT", "")

def fail(message, code=100):
    print(message, file=sys.stderr)
    raise SystemExit(code)

def tools():
    target = root / "pg-bin"
    target.mkdir(exist_ok=True)
    for tool in ("postgres", "initdb", "pg_ctl", "psql"):
        p = target / tool
        version = "17.1" if fault == "version" else "18.1"
        p.write_text("#!/bin/sh\nprintf '%s\\n' '" + tool + " (PostgreSQL) " + version + "'\n")
        p.chmod(0o755)

if command == "id":
    assert args == ["-u"]
    print("0" if fault == "root" else "1001")
elif command == "dpkg":
    assert args == ["--print-architecture"]
    print("arm64" if fault == "architecture" else "amd64")
elif command == "sudo":
    assert args[0] == "-n" and args[1] in ("apt-get", "rm")
    os.execvpe(args[1], args[1:], os.environ)
elif command == "curl":
    assert "--fail" in args and "--tlsv1.2" in args
    assert args[args.index("--proto") + 1] == "=https"
    assert args[args.index("--proto-redir") + 1] == "=https"
    assert "https://www.postgresql.org/media/keys/ACCC4CF8.asc" in args
    if fault == "curl":
        fail("controlled HTTPS fetch failure", 22)
    pathlib.Path(args[args.index("--output") + 1]).write_text("PGDG_KEY")
elif command == "gpg":
    assert args[:3] == ["--batch", "--show-keys", "--with-colons"]
    assert pathlib.Path(args[3]).read_text() == "PGDG_KEY"
    if fault == "gpg":
        fail("controlled malformed key", 2)
    fingerprint = "BAD" if fault == "fingerprint" else "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"
    print("fpr:::::::::" + fingerprint + ":")
elif command == "apt-get":
    options = {}
    while args and args[0] == "-o":
        key, value = args[1].split("=", 1)
        options[key] = value
        args = args[2:]
    action = args[0]
    if "Dir::Etc::sourcelist" not in options:
        sources = (root / "system.sources").read_text()
        with (root / "calls.jsonl").open("a") as out:
            out.write(json.dumps({"action": action, "sources": sources, "scoped": False}) + "\n")
        fail("https://packages.microsoft.com/ubuntu/24.04/prod: 403 Forbidden; repository is not signed")
    main = pathlib.Path(options["Dir::Etc::sourcelist"])
    parts = pathlib.Path(options["Dir::Etc::sourceparts"])
    lists = pathlib.Path(options["Dir::State::lists"])
    assert main.parent == parts.parent == lists.parent
    assert str(main.parent).startswith(str(root / "apt."))
    # APT's sandbox user must be able to traverse source/key parents.
    for p in (main, parts, lists):
        assert p.stat().st_mode & stat.S_IROTH
        current = p if p.is_dir() else p.parent
        while current != root:
            assert current.stat().st_mode & stat.S_IXOTH
            current = current.parent
    assert options["Dir::Cache::pkgcache"] == options["Dir::Cache::srcpkgcache"] == ""
    records = [main.read_text()] + [p.read_text() for p in sorted(parts.glob("*.sources"))]
    sources = "\n".join(records)
    pgdg = "https://apt.postgresql.org/pub/repos/apt" in sources
    with (root / "calls.jsonl").open("a") as out:
        out.write(json.dumps({"action": action, "arguments": args, "sources": sources,
                              "scoped": True, "options": options, "pgdg": pgdg}) + "\n")
    allowed = {"https://archive.ubuntu.com/ubuntu", "https://security.ubuntu.com/ubuntu",
               "https://apt.postgresql.org/pub/repos/apt"}
    uris = [line.split(": ", 1)[1] for line in sources.splitlines() if line.startswith("URIs: ")]
    if any(uri not in allowed for uri in uris):
        fail("unapproved source")
    assert len(uris) == (3 if pgdg else 2)
    assert "Suites: noble noble-updates" in sources and "Suites: noble-security" in sources
    if pgdg:
        assert "Suites: noble-pgdg" in sources
    keys = [pathlib.Path(line.split(": ", 1)[1]) for line in sources.splitlines() if line.startswith("Signed-By: ")]
    assert len(keys) == len(uris) and all(p.is_file() and p.stat().st_mode & stat.S_IROTH for p in keys)
    assert keys[0].read_text() == keys[1].read_text() == "UBUNTU_KEY"
    assert not pgdg or keys[2].read_text() == "PGDG_KEY"
    for option in ("Acquire::AllowInsecureRepositories", "Acquire::AllowDowngradeToInsecureRepositories",
                   "APT::Get::AllowUnauthenticated"):
        assert options[option] == "false"
    stage = "pgdg" if pgdg else "ubuntu"
    if action == "update":
        # APT can otherwise return zero on a partial fetch failure.
        if fault == stage + "-partial-update":
            if options.get("APT::Update::Error-Mode") == "any":
                fail("controlled partial index failure")
            raise SystemExit(0)
        if fault == stage + "-signature":
            fail("controlled invalid InRelease signature")
        if fault == stage + "-update":
            fail("controlled index fetch failure")
        assert options["APT::Update::Error-Mode"] == "any"
        (lists / (stage + ".index")).write_text("verified index")
    elif action == "install":
        assert args[1:3] == ["-y", "--no-install-recommends"]
        assert (lists / (stage + ".index")).is_file()
        if fault == stage + "-install":
            fail("controlled package install failure")
        if pgdg:
            assert args[3:] == ["postgresql-18", "postgresql-client-18"]
            tools()
        else:
            assert args[3:] == ["ca-certificates", "curl", "gnupg"]
    else:
        fail("unexpected APT action")
else:
    fail("unexpected command " + command)
'''


class NativePostgresToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pg18-command-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for command in ("id", "dpkg", "sudo", "apt-get", "curl", "gpg"):
            p = self.bin / command
            p.write_text("#!" + sys.executable + "\n" + COMMAND_FIXTURE)
            p.chmod(0o755)
        self.os_release = self.root / "os-release"
        self.os_release.write_text("ID=ubuntu\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n")
        (self.root / "ubuntu-key.gpg").write_text("UBUNTU_KEY")
        self.system_sources = "URIs: https://packages.microsoft.com/ubuntu/24.04/prod\n"
        (self.root / "system.sources").write_text(self.system_sources)
        self.shell = workflow_shell()
        for original, replacement in {
            "/usr/lib/postgresql/18/bin": str(self.root / "pg-bin"),
            "/etc/os-release": str(self.os_release),
            "/usr/share/keyrings/ubuntu-archive-keyring.gpg": str(self.root / "ubuntu-key.gpg"),
            "/tmp/yueops-pg18-apt.XXXXXX": str(self.root / "apt.XXXXXX"),
        }.items():
            self.assertEqual(self.shell.count(original), 1, original)
            self.shell = self.shell.replace(original, replacement)

    def run_step(self, fault="", shell=None):
        result = subprocess.run(
            ["/bin/bash", "-c", self.shell if shell is None else shell],
            env=os.environ | {"PATH": str(self.bin) + os.pathsep + os.defpath,
                              "FIXTURE_ROOT": str(self.root), "FIXTURE_FAULT": fault,
                              "GITHUB_PATH": str(self.root / "github-path")},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual((self.root / "system.sources").read_text(), self.system_sources)
        self.assertEqual(list(self.root.glob("apt.*")), [], "temporary APT state was not cleaned")
        return result

    def calls(self):
        p = self.root / "calls.jsonl"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def preinstall(self, missing=None, version="18.2"):
        target = self.root / "pg-bin"
        target.mkdir()
        for name in ("postgres", "initdb", "pg_ctl", "psql"):
            if name == missing:
                continue
            p = target / name
            p.write_text("#!/bin/sh\nprintf '%s\\n' '" + name + " (PostgreSQL) " + version + "'\n")
            p.chmod(0o755)

    def test_install_excludes_unrelated_system_source_and_uses_fresh_lists(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual([c["action"] for c in calls], ["update", "install", "update", "install"])
        self.assertEqual([c["pgdg"] for c in calls], [False, False, True, True])
        self.assertTrue(all(c["scoped"] for c in calls))
        self.assertTrue(all("microsoft" not in c["sources"] for c in calls))
        self.assertEqual((self.root / "github-path").read_text(), str(self.root / "pg-bin") + "\n")

    def test_original_unscoped_update_reproduces_microsoft_failure(self):
        # Replace only the actual first update invocation with its original form.
        self.assertEqual(self.shell.count('"${apt[@]}" update'), 2)
        result = self.run_step(shell=self.shell.replace('"${apt[@]}" update', '"${elevate[@]}" apt-get update', 1))
        self.assertEqual(result.returncode, 100)
        self.assertIn("403 Forbidden", result.stderr)
        self.assertFalse(self.calls()[0]["scoped"])

    def test_existing_install_still_checks_tools_and_version_without_apt(self):
        self.preinstall()
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])

    def test_wrong_os_is_rejected_before_apt(self):
        self.os_release.write_text("ID=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n")
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_wrong_release_is_rejected_before_apt(self):
        self.os_release.write_text("ID=ubuntu\nVERSION_ID=22.04\nVERSION_CODENAME=noble\n")
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_wrong_codename_is_rejected_before_apt(self):
        self.os_release.write_text("ID=ubuntu\nVERSION_ID=24.04\nVERSION_CODENAME=jammy\n")
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_wrong_architecture_is_rejected_before_apt(self):
        self.assertNotEqual(self.run_step("architecture").returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_missing_ubuntu_trust_is_rejected_before_apt(self):
        (self.root / "ubuntu-key.gpg").unlink()
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_unapproved_source_is_fatal(self):
        result = self.run_step(shell=self.shell.replace("https://archive.ubuntu.com/ubuntu", "https://unapproved.invalid/ubuntu"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unapproved source", result.stderr)
        self.assertEqual(len(self.calls()), 1)

    def test_key_fetch_parse_and_fingerprint_fail_before_pgdg(self):
        for fault in ("curl", "gpg", "fingerprint"):
            with self.subTest(fault=fault):
                result = self.run_step(fault)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c["pgdg"] for c in self.calls()))
                self.assertFalse((self.root / "github-path").exists())

    def test_all_apt_failures_remain_fatal(self):
        for stage in ("ubuntu", "pgdg"):
            for kind in ("update", "partial-update", "signature", "install"):
                with self.subTest(stage=stage, kind=kind):
                    result = self.run_step(stage + "-" + kind)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((self.root / "github-path").exists())
                    self.assertFalse((self.root / "pg-bin").exists())

    def test_wrong_installed_major_is_rejected(self):
        result = self.run_step("version")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "github-path").exists())

    def test_existing_wrong_major_is_rejected(self):
        self.preinstall(version="17.2")
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_existing_missing_tool_is_rejected(self):
        self.preinstall(missing="pg_ctl")
        self.assertNotEqual(self.run_step().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_root_cannot_pass_fixture_preflight(self):
        self.preinstall()
        result = self.run_step("root")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("require a non-root runner", result.stdout)
        self.assertFalse((self.root / "github-path").exists())


if __name__ == "__main__":
    unittest.main()
