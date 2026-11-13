"""Container validation stays pinned; Board visual validation uses the host."""

from __future__ import annotations

from workflow_source import workflow_text
import re
import yaml
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
IMAGE = ROOT / "images" / "yueops-ci-toolchain"
RETIRED = (
    "scripts/install-yueops-pg18-toolchain.sh",
    "scripts/activate-yueops-pg18-toolchain.sh",
    "scripts/pg18-toolchain-roundtrip.sh",
    "tests/test_native_postgres_toolchain.py",
)


class CiToolchainImageTest(unittest.TestCase):
    def test_retired_apt_installer_is_gone(self) -> None:
        for relative in RETIRED:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists(), relative)

    def test_validate_pins_the_image_and_does_not_apt(self) -> None:
        workflow = workflow_text(WORKFLOW)
        validate = workflow.split("\n  validate:\n", 1)[1].split(
            "\n  validation-evidence:\n", 1
        )[0]
        self.assertRegex(
            validate,
            r"ghcr\.io/onesyue/yueops-ci-toolchain@sha256:[0-9a-f]{64}",
        )
        self.assertNotIn("DIGEST_PLACEHOLDER", workflow)
        job = yaml.safe_load(workflow)['jobs']['validate']
        self.assertRegex(job['container']['image'],
                         r"^\$\{\{ matrix.board_role != 'e2e' && 'ghcr\.io/onesyue/yueops-ci-toolchain@sha256:[0-9a-f]{64}' \|\| '' \}\}$")
        for step in job['steps']:
            if 'apt-get' in step.get('run', ''):
                self.assertEqual(step['if'], "matrix.board_role == 'e2e'")
        self.assertNotIn("install-yueops-pg18", validate)
        self.assertNotIn("install-native-nginx.sh", validate)
        self.assertIn("sing-box-1.14 version", validate)
        self.assertIn("shell: bash", validate)

    def test_host_e2e_keeps_python_temp_database_and_visual_contract(self) -> None:
        job = yaml.safe_load(WORKFLOW.read_text())['jobs']['validate']
        steps = {step.get('name'): step for step in job['steps']}
        self.assertEqual(job['env']['TMPDIR'],
                         "${{ matrix.board_role == 'e2e' && '/tmp' || '/__w/_temp' }}")
        host_condition = "matrix.board_role == 'e2e' && (github.event_name != 'workflow_dispatch' || github.event.inputs.runner != 'yue-local-release')"
        for name in ('Set up Python for host Board e2e', 'Select Python for host Board e2e'):
            self.assertEqual(steps[name]['if'], host_condition)
        for name in ('Set up Python on GitHub-hosted runner', 'Select Python on GitHub-hosted runner'):
            self.assertEqual(steps[name]['if'], host_condition.replace("== 'e2e'", "!= 'e2e'"))
        self.assertEqual(steps['Set up Python for host Board e2e']['with']['python-version'], '3.13')
        self.assertIn('command -v python3', steps['Select Python for host Board e2e']['run'])
        e2e = steps['Validate YueBoard end-to-end suite']
        self.assertIn('--database-adapter loopback', e2e['run'])
        for name, database in [('YUEBOARD_ADMIN_DATABASE_URL', 'postgres'),
                               ('YUEBOARD_E2E_DATABASE_URL', 'yueboard_e2e?sslmode=disable')]:
            self.assertEqual(e2e['env'][name],
                "${{ github.event_name == 'workflow_dispatch' && github.event.inputs.runner == 'yue-local-release' && 'postgres://postgres:ci@127.0.0.1:55434/" + database +
                "' || 'postgres://postgres:ci@127.0.0.1:5432/" + database + "' }}")
        executor = (ROOT / 'scripts/board-validation.sh').read_text()
        self.assertIn('pnpm --dir test/e2e test --update-snapshots=none', executor)
        self.assertNotIn('--update-snapshots=all', executor)

    def test_image_build_pins_uv_and_the_runtime_tools(self) -> None:
        digest = (IMAGE / "uv.sha256").read_text(encoding="utf-8").strip()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        dockerfile = (IMAGE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG UV_SHA256", dockerfile)
        self.assertIn('echo "$UV_SHA256  /tmp/uv.tgz" | sha256sum -c', dockerfile)
        for needle in (
            "postgresql-18 postgresql-client-18 libpq-dev",
            "pg_config.h",
            "plpgsql.so",
            "dict_snowball.so",
            "sing-box-1.14",
            "go1.27.4",
            "Python-3.13.12.tgz",
            "12e7cb170ad2d1a69aee96a1cc7fc8de5b1e97a2bdac51683a3db016ec9a2996",
            "pidfd_open",
            "ln -sfn /usr/local/bin/python3 /usr/bin/python3",
            "openssh-client",
            "rsync",
            "docker-hostpath.sh",
            "bind9-dnsutils",
            "docker-compose-v2",
            "test -x /usr/bin/bc",
            "ENV USER=runner",
            "USER runner",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, dockerfile)
        selfcheck = (IMAGE / "selfcheck.sh").read_text(encoding="utf-8")
        self.assertIn('test -f "$(pg_config --includedir)/pg_config.h"', selfcheck)
        self.assertIn("test -x /usr/bin/python3", selfcheck)
        self.assertIn("ssh-keygen", selfcheck)
        self.assertIn("pidfd_open", selfcheck)
        self.assertIn("rsync", selfcheck)
        self.assertIn("dig", selfcheck)
        self.assertIn(" bc", selfcheck)
        self.assertIn('os.environ["USER"] == "runner"', selfcheck)
        self.assertIn("docker compose version", selfcheck)
        rebuild = (ROOT / ".github" / "workflows" / "ci-toolchain.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("images/yueops-ci-toolchain/uv.sha256", rebuild)
        self.assertRegex(
            rebuild,
            re.compile(r"uses: docker/(?:login|build-push)-action@[0-9a-f]{40}"),
        )
        self.assertIn("provenance: false", rebuild)
        self.assertIn("yueops-ci-toolchain-selfcheck", rebuild)

    def test_docker_wrapper_rewrites_host_work_path(self) -> None:
        wrapper = IMAGE / "docker-hostpath.sh"
        fake = ROOT / ".docker-fake-not-used"
        # The wrapper execs DOCKER_REAL. A shell stub records its arguments.
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / "docker"
            stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            stub.chmod(0o755)
            completed = subprocess.run(
                ["bash", str(wrapper), "run", "-v",
                 "/__w/yueto-ci/yueto-ci/scripts/yueops-harden.sh:/review/yueops-harden.sh:ro",
                 "--mount", "type=bind,source=/__w/yueto-ci/yueto-ci,target=/src"],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "DOCKER_REAL": str(stub)},
            )
        lines = completed.stdout.splitlines()
        self.assertEqual(
            lines[2],
            "/home/runner/work/yueto-ci/yueto-ci/scripts/yueops-harden.sh:/review/yueops-harden.sh:ro",
        )
        self.assertEqual(
            lines[4],
            "type=bind,source=/home/runner/work/yueto-ci/yueto-ci,target=/src",
        )
        self.assertFalse(fake.exists())


if __name__ == "__main__":
    unittest.main()
