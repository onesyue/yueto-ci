"""Execute the installer with controlled external commands and files.

The fixtures model APT trust/fetch failures, not cryptography or a real install.
The workflow names the installer once. Shards unpack its archive and never apt.
DNS resolution retries; a package miss or a bad signature does not.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEP = "      - name: Install native YueOps PostgreSQL 18 test toolchain\n"
FINGERPRINT = "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"


def workflow_shell():
    workflow = (ROOT / ".github/workflows/build.yml").read_text()
    assert workflow.count(STEP) == 1
    assert "bash scripts/install-yueops-pg18-toolchain.sh\n" in workflow
    # The package line lives in the installer. Shards must not apt-install it.
    assert "postgresql-18" not in workflow
    return (ROOT / "scripts/install-yueops-pg18-toolchain.sh").read_text()


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
elif command == "sleep":
    assert len(args) == 1
    with (root / "sleeps").open("a") as out:
        out.write(args[0] + "\n")
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
        if fault == "ubuntu-resolve" and stage == "ubuntu":
            seen = sum(
                1 for line in (root / "calls.jsonl").read_text().splitlines()
                if json.loads(line)["action"] == "update" and not json.loads(line)["pgdg"])
            if seen == 1:
                fail("Temporary failure resolving 'archive.ubuntu.com'")
        if fault == "ubuntu-resolve-exhausted" and stage == "ubuntu":
            fail("Temporary failure resolving 'archive.ubuntu.com'")
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
        for command in ("id", "dpkg", "sudo", "apt-get", "curl", "gpg", "sleep"):
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
            "/usr/share/postgresql/18": str(self.root / "pg-share"),
            "/etc/os-release": str(self.os_release),
            "/usr/share/keyrings/ubuntu-archive-keyring.gpg": str(self.root / "ubuntu-key.gpg"),
            "/tmp/yueops-pg18-apt.XXXXXX": str(self.root / "apt.XXXXXX"),
        }.items():
            self.assertEqual(self.shell.count(original), 1, original)
            self.shell = self.shell.replace(original, replacement)

    def run_step(self, fault="", shell=None, args=None):
        body = self.shell if shell is None else shell
        script = self.root / "install.sh"
        script.write_text(body)
        script.chmod(0o755)
        retry = self.root / "ci-retry.sh"
        if not retry.exists():
            retry.write_bytes((ROOT / "scripts/ci-retry.sh").read_bytes())
            retry.chmod(0o755)
        result = subprocess.run(
            ["/bin/bash", str(script), *(args or [])],
            env=os.environ | {"PATH": str(self.bin) + os.pathsep + os.defpath,
                              "FIXTURE_ROOT": str(self.root), "FIXTURE_FAULT": fault,
                              "GITHUB_PATH": str(self.root / "github-path")},
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual((self.root / "system.sources").read_text(), self.system_sources)
        self.assertEqual(list(self.root.glob("apt.*")), [], "temporary APT state was not cleaned")
        return result

    def calls(self):
        p = self.root / "calls.jsonl"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def sleeps(self):
        path = self.root / "sleeps"
        return path.read_text().splitlines() if path.exists() else []

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

    def test_one_dns_resolution_failure_retries_then_installs(self):
        result = self.run_step("ubuntu-resolve")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [c["action"] for c in self.calls()],
            ["update", "update", "install", "update", "install"],
        )
        self.assertEqual(self.sleeps(), ["2"])
        self.assertIn("transient failure on attempt 1/3", result.stderr)
        self.assertIn("Temporary failure resolving", result.stderr)
        self.assertEqual((self.root / "github-path").read_text(), str(self.root / "pg-bin") + "\n")

    def test_repeated_dns_resolution_failure_stays_fatal(self):
        result = self.run_step("ubuntu-resolve-exhausted")
        self.assertEqual(result.returncode, 100, result.stderr)
        self.assertEqual([c["action"] for c in self.calls()], ["update", "update", "update"])
        self.assertEqual(self.sleeps(), ["2", "4"])
        self.assertFalse((self.root / "github-path").exists())
        self.assertFalse((self.root / "pg-bin").exists())

    def seed_prefix(self, *, libc=False):
        self.preinstall()
        lib = self.root / "lib"
        lib.mkdir()
        (lib / "plpgsql.so").write_bytes(b"plpgsql")
        (lib / "dict_snowball.so").write_bytes(b"snowball")
        if libc:
            (lib / "libc.so.6").write_bytes(b"not-the-loader")
        share = self.root / "pg-share"
        share.mkdir()
        (share / "postgres.bki").write_text("bki")

    def test_pack_reuses_installed_tree_without_apt(self):
        self.seed_prefix()
        archive = self.root / "out.tar"
        result = self.run_step(args=["pack", str(archive)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        listing = subprocess.run(["tar", "-tf", str(archive)], capture_output=True, text=True, check=False)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        names = [line.rstrip("/") for line in listing.stdout.splitlines()]
        self.assertTrue(any(line.endswith("postgres") for line in names), listing.stdout)
        self.assertTrue(any(line.endswith("plpgsql.so") for line in names), listing.stdout)
        self.assertTrue(any(line.endswith("dict_snowball.so") for line in names), listing.stdout)
        self.assertTrue(any(line.endswith("postgres.bki") for line in names), listing.stdout)
        self.assertFalse(any("libc.so" in line or "ld-linux" in line for line in names), listing.stdout)

    def test_pack_dereferences_external_soname_link(self):
        import tarfile
        self.seed_prefix()
        with tempfile.TemporaryDirectory(prefix="pg18-external-lib-") as directory:
            external = Path(directory)
            target = external / "libfixture.so.1.2.3"
            target.write_bytes(b"external dependency bytes")
            soname = external / "libfixture.so.1"
            soname.symlink_to(target.name)
            ldd = self.bin / "ldd"
            ldd.write_text("#!/bin/sh\nprintf '%s\\n' 'libfixture.so.1 => " + str(soname) + " (0x1)'\n")
            ldd.chmod(0o755)
            archive = self.root / "out.tar"
            result = self.run_step(args=["pack", str(archive)])
            self.assertEqual(result.returncode, 0, result.stderr)
            with tarfile.open(archive) as packed:
                member = next(m for m in packed.getmembers() if m.name.endswith("/lib/libfixture.so.1"))
                self.assertTrue(member.isfile(), "SONAME must carry bytes, not a link to an unpacked target")
                content = packed.extractfile(member)
                assert content is not None
                self.assertEqual(content.read(), target.read_bytes())

    def test_pack_refuses_to_carry_libc(self):
        self.seed_prefix(libc=True)
        result = self.run_step(args=["pack", str(self.root / "out.tar")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to pack libc", result.stderr)
        self.assertFalse((self.root / "out.tar").exists())

    def test_activate_missing_archive_fails_closed_without_apt(self):
        script = (ROOT / "scripts/activate-yueops-pg18-toolchain.sh").read_text()
        self.assertNotIn("apt-get", script)
        self.assertNotIn("apt ", script)
        self.assertNotIn("tar -C / ", script)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/activate-yueops-pg18-toolchain.sh"), str(self.root / "missing.tar")],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_activate_unpacks_under_runner_temp_and_links_only_the_prefix(self):
        script = (ROOT / "scripts/activate-yueops-pg18-toolchain.sh").read_text()
        self.assertNotIn("tar -C / ", script)
        self.assertNotIn("apt-get", script)
        stage = self.root / "stage"
        bindir = stage / "usr/lib/postgresql/18/bin"
        libdir = stage / "usr/lib/postgresql/18/lib"
        sharedir = stage / "usr/share/postgresql/18"
        bindir.mkdir(parents=True)
        libdir.mkdir(parents=True)
        sharedir.mkdir(parents=True)
        for name in ("postgres", "initdb", "pg_ctl", "psql"):
            tool = bindir / name
            tool.write_text("#!/bin/sh\nprintf '%s\\n' 'tool (PostgreSQL) 18.6'\n")
            tool.chmod(0o755)
        (libdir / "plpgsql.so").write_bytes(b"plpgsql")
        (libdir / "dict_snowball.so").write_bytes(b"snowball")
        (sharedir / "postgres.bki").write_text("bki")
        archive = self.root / "pg18-toolchain.tar"
        packed = subprocess.run(["tar", "-C", str(stage), "-cf", str(archive), "."], check=False)
        self.assertEqual(packed.returncode, 0)
        runner = self.root / "runner"
        sysroot = self.root / "sysroot"
        runner.mkdir()
        env = os.environ | {
            "RUNNER_TEMP": str(runner),
            "YUEOPS_PG18_SYSROOT": str(sysroot),
            "GITHUB_PATH": str(self.root / "github-path"),
            "GITHUB_ENV": str(self.root / "github-env"),
            "LD_LIBRARY_PATH": "/opt/hostedtoolcache/Python/lib",
        }
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/activate-yueops-pg18-toolchain.sh"), str(archive)],
            capture_output=True, text=True, timeout=20, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        link = sysroot / "usr/lib/postgresql/18"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (runner / "yueops-pg18/usr/lib/postgresql/18").resolve())
        self.assertTrue((link / "lib/plpgsql.so").is_file())
        self.assertEqual((self.root / "github-path").read_text().strip(), str(link / "bin"))
        private_lib = f"{runner}/yueops-pg18/usr/lib/postgresql/18/lib"
        self.assertIn(
            f"LD_LIBRARY_PATH={private_lib}:/opt/hostedtoolcache/Python/lib\n",
            (self.root / "github-env").read_text(),
        )
        self.assertNotIn(f"LD_LIBRARY_PATH={private_lib}\n", (self.root / "github-env").read_text())
        self.assertFalse((self.root / "usr").exists())

    def test_unpacked_tree_initdb_creates_plpgsql(self):
        homes = (
            Path("/opt/homebrew/opt/postgresql@18"),
            Path("/usr/local/opt/postgresql@18"),
            Path("/usr/lib/postgresql/18"),
        )
        home = next((path for path in homes if (path / "bin" / "initdb").is_file()), None)
        if home is None:
            self.skipTest("PostgreSQL 18 initdb is not installed on this runner")
        env = os.environ | {
            "PATH": str(home / "bin") + os.pathsep + os.defpath,
            "LC_ALL": "C",
        }
        result = subprocess.run(
            [str(ROOT / "scripts/pg18-toolchain-roundtrip.sh")],
            capture_output=True, text=True, timeout=60, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "plpgsql")

    def test_toolchain_failure_makes_validation_evidence_reject_a_skipped_matrix(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        validate = workflow.split("\n  validate:\n", 1)[1].split("\n  validation-evidence:\n", 1)[0]
        gate = [line.strip() for line in validate.splitlines() if "yueops-pg18-toolchain.result" in line]
        self.assertEqual(gate, [
            "if: always() && needs.plan.result == 'success' && (needs.yueops-pg18-toolchain.result == 'success' || needs.yueops-pg18-toolchain.result == 'skipped')",
        ])
        evidence = workflow.split("\n  validation-evidence:\n", 1)[1].split("\n  build:\n", 1)[0]
        self.assertIn("if: always() && needs.plan.result == 'success'\n", evidence)
        self.assertIn("VALIDATION_RESULT: ${{ needs.validate.result }}", evidence)
        head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        previous = {key: os.environ.get(key) for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_REPOSITORY")}
        os.environ["GITHUB_SHA"] = head
        os.environ["GITHUB_RUN_ID"] = "431"
        os.environ["GITHUB_RUN_ATTEMPT"] = "1"
        os.environ["GITHUB_REPOSITORY"] = "onesyue/yueto-ci"
        try:
            spec = importlib.util.spec_from_file_location("pg18_pytest_shards", ROOT / "scripts/pytest-shards.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            body = {
                "schema": 1,
                "identity": module.workflow_identity(),
                "mode": "none",
                "source_revision": None,
                "board_revision": None,
                "ops_plan": None,
                "validation_matrix": [{"validation": "yueboard"}],
            }
            digest = module.sha(module.encoded(body))
            with self.assertRaisesRegex(ValueError, "selected validation matrix did not succeed"):
                module.join(body | {"admission_sha256": digest}, None, "skipped", digest)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_shards_unpack_one_archive_and_do_not_apt(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        toolchain, rest = workflow.split("  yueops-pg18-toolchain:\n", 1)[1].split("  validate:\n", 1)
        validate = rest.split("\n  validation-evidence:\n", 1)[0]
        self.assertIn("fail-fast: false\n", validate)
        self.assertIn("needs: [plan, yueops-pg18-toolchain]\n", "  validate:\n" + validate)
        self.assertNotIn("apt-get", toolchain)
        activate = validate.split(
            "      - name: Activate YueOps PostgreSQL 18 toolchain\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn(".ci-policy/scripts/activate-yueops-pg18-toolchain.sh", activate)
        self.assertNotIn("apt-get", activate)
        self.assertNotIn("continue-on-error", activate)
if __name__ == "__main__":
    unittest.main()
