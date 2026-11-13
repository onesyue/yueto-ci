"""Offline real-shell consumers of the single lint authority; no tool downloads."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / 'scripts/lint-tool-versions.sh'
BASH = shutil.which('bash') or '/bin/bash'
PINS = {
    'GOLANGCI_LINT_VERSION': '2.14.0',
    'GOLANGCI_LINT_SHA256': 'ab90aeb7b066f92a33415b638a50fe5344bbb75a0d32ad30cc248d88f81032ab',
    'GOVULNCHECK_VERSION': 'v1.8.0',
    'SQUAWK_VERSION': '2.60.0',
    'SQUAWK_SHA256': '708d77899e2b43e0d21cb811023dbbcfb3b8220b0c0b7e71c6e73568be7716e5',
    'ACTIONLINT_VERSION': '1.7.12',
    'ACTIONLINT_ARCHIVE_SHA256': '8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8',
}


class LintAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        for name in ('lint-tool-versions.sh', 'install-board-quality-tools.sh',
                     'ops-validation-migrations.sh', 'ci-retry.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, self.scripts / name)
        self.authority = self.scripts / 'lint-tool-versions.sh'
        (self.root / '.ci-policy').symlink_to(self.root, target_is_directory=True)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.dest = self.root / 'destination'
        self.calls = self.root / 'calls'
        self.archive = self.root / 'download'
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(('GIT_', 'GH_', 'GITHUB_', 'GOLANGCI_', 'GOVULNCHECK_', 'SQUAWK_', 'ACTIONLINT_', 'LINT_'))}
        self.env.update(PATH=f'{self.bin}:/usr/bin:/bin', RUNNER_TEMP=str(self.root),
                        GITHUB_PATH=str(self.root / 'github-path'), MIGRATION_BASE='fixture',
                        CALLS=str(self.calls), DOWNLOAD=str(self.archive))
        self.shim('uname', 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac\n')
        self.shim('curl', '''printf 'curl %s\n' "$*" >> "$CALLS"
[ "${DOWNLOAD_FAIL:-0}" = 0 ] || exit 7
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then cp "$DOWNLOAD" "$2"; exit; fi
  shift
done
exit 98
''')
        self.shim('sleep', ':\n')
        checksum = shutil.which('gsha256sum') or shutil.which('sha256sum')
        self.assertIsNotNone(checksum, 'GNU checksum tool is required for installer fixtures')
        (self.bin / 'sha256sum').symlink_to(str(checksum))
        (self.bin / 'python3').symlink_to(sys.executable)
        (self.scripts / 'changed-migrations.py').write_text(
            "import os,sys\n"
            "if os.environ.get('NO_MIGRATIONS') != '1': sys.stdout.buffer.write(b'fixture.sql\\0')\n")
        self.shim('go', '''printf 'go %s\n' "$*" >> "$CALLS"
[ "${GO_FAIL:-0}" = 0 ] || exit 38
printf '#!/bin/bash\\necho govulncheck %s\\n' "${FIXTURE_GOVULN_VERSION:-v1.8.0}" > "$GOBIN/govulncheck"
chmod +x "$GOBIN/govulncheck"
''')

    def shim(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text('#!/bin/bash\nset -eu\n' + body)
        path.chmod(0o755)

    def replace_pin(self, name: str, value: str) -> None:
        text = self.authority.read_text()
        lines = [f"readonly {name}='{value}'" if line.startswith(f'readonly {name}=') else line
                 for line in text.splitlines()]
        self.authority.write_text('\n'.join(lines) + '\n')

    def prepare_download(self, kind: str, version: str) -> None:
        body = f'#!/bin/bash\nprintf "executed {kind} %s\\n" "$*" >> "$CALLS"\necho {kind} {version}\n'.encode()
        if kind == 'squawk':
            self.archive.write_bytes(body)
            pin = 'SQUAWK_SHA256'
        else:
            member = f'golangci-lint-{version}-linux-amd64/golangci-lint' if kind == 'golangci-lint' else 'actionlint'
            with tarfile.open(self.archive, 'w:gz') as archive:
                info = tarfile.TarInfo(member)
                info.size = len(body)
                info.mode = 0o755
                archive.addfile(info, io.BytesIO(body))
            pin = 'GOLANGCI_LINT_SHA256' if kind == 'golangci-lint' else 'ACTIONLINT_ARCHIVE_SHA256'
        self.replace_pin(pin, hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def run_consumer(self, consumer: str, **extra: str) -> subprocess.CompletedProcess[str]:
        if consumer == 'board':
            argv = [BASH, str(self.scripts / 'install-board-quality-tools.sh'), str(self.dest)]
        elif consumer == 'squawk':
            argv = [BASH, str(self.scripts / 'ops-validation-migrations.sh')]
        else:
            workflow = (ROOT / '.github/workflows/policy-ci.yml').read_text()
            step = workflow.split('      - name: Install pinned actionlint\n', 1)[1]
            body = step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
            argv = [BASH, '-c', textwrap.dedent(body)]
        return subprocess.run(argv, cwd=self.root, env=self.env | extra,
                              text=True, capture_output=True, timeout=15)

    def log(self) -> str:
        return self.calls.read_text() if self.calls.exists() else ''

    def test_authority_preserves_reviewed_pins(self) -> None:
        result = subprocess.run([BASH, '-eu', '-c',
                                 'source "$1"; ' + '; '.join(f'printf "%s\\n" "${key}"' for key in PINS),
                                 'fixture', str(AUTHORITY)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), list(PINS.values()))

    def test_real_installers_use_mutated_authority_not_environment(self) -> None:
        for consumer, kind, pin in [('board', 'golangci-lint', 'GOLANGCI_LINT_VERSION'),
                                    ('squawk', 'squawk', 'SQUAWK_VERSION'),
                                    ('actionlint', 'actionlint', 'ACTIONLINT_VERSION')]:
            with self.subTest(consumer=consumer):
                self.authority.write_text(AUTHORITY.read_text())
                self.replace_pin(pin, '9.8.7')
                self.replace_pin('GOVULNCHECK_VERSION', 'v9.8.7')
                self.prepare_download(kind, '9.8.7')
                self.calls.unlink(missing_ok=True)
                result = self.run_consumer(consumer, **{pin: 'evil-env', 'GOVULNCHECK_VERSION': 'evil-env',
                                                       'FIXTURE_GOVULN_VERSION': 'v9.8.7'})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('/v9.8.7/', self.log())
                self.assertIn(f'executed {kind}', self.log())
                self.assertNotIn('evil-env', self.log())
                if consumer == 'board':
                    self.assertIn('go install golang.org/x/vuln/cmd/govulncheck@v9.8.7', self.log())
                    self.assertTrue((self.dest / 'golangci-lint').exists())
                    self.assertTrue((self.dest / 'govulncheck').exists())
                if consumer == 'squawk':
                    self.assertIn('--pg-version=15.0', self.log())
                    self.assertIn('fixture.sql', self.log())

    def test_bad_digest_transport_and_binary_version_fail(self) -> None:
        for consumer, kind, version, hash_pin in [
            ('board', 'golangci-lint', '2.14.0', 'GOLANGCI_LINT_SHA256'),
            ('squawk', 'squawk', '2.60.0', 'SQUAWK_SHA256'),
            ('actionlint', 'actionlint', '1.7.12', 'ACTIONLINT_ARCHIVE_SHA256')]:
            for failure in ('digest', 'transport', 'version'):
                with self.subTest(consumer=consumer, failure=failure):
                    self.authority.write_text(AUTHORITY.read_text())
                    self.prepare_download(kind, '0.0.0' if failure == 'version' else version)
                    if failure == 'digest':
                        self.replace_pin(hash_pin, '0' * 64)
                    self.calls.unlink(missing_ok=True)
                    result = self.run_consumer(consumer, DOWNLOAD_FAIL='1' if failure == 'transport' else '0')
                    # actionlint's existing workflow prints, but does not compare its version.
                    # Keep that behavior; checksum verification remains its integrity authority.
                    if consumer == 'actionlint' and failure == 'version':
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                    if failure != 'version':
                        self.assertNotIn('executed', self.log())

    def test_board_path_fast_path_and_go_failure(self) -> None:
        self.shim('govulncheck', 'echo govulncheck v1.8.0\n')
        self.shim('golangci-lint', 'echo golangci-lint 2.14.0\n')
        result = self.run_consumer('board')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.dest / 'golangci-lint').exists())
        self.assertTrue((self.dest / 'govulncheck').exists())
        self.assertEqual(self.log(), '')
        (self.bin / 'govulncheck').unlink()
        (self.bin / 'golangci-lint').unlink()
        self.prepare_download('golangci-lint', '2.14.0')
        result = self.run_consumer('board', GO_FAIL='1')
        self.assertEqual(result.returncode, 38)

    def test_missing_malformed_or_empty_authority_never_executes_tools(self) -> None:
        for corruption in ('missing', 'empty', 'version', 'hash', 'omitted'):
            for consumer in ('board', 'squawk', 'actionlint'):
                with self.subTest(corruption=corruption, consumer=consumer):
                    self.authority.write_text(AUTHORITY.read_text())
                    if corruption == 'missing':
                        self.authority.unlink()
                    elif corruption == 'empty':
                        self.authority.write_text('')
                    elif corruption == 'version':
                        self.replace_pin('GOLANGCI_LINT_VERSION', 'not-a-version')
                    elif corruption == 'hash':
                        self.replace_pin('SQUAWK_SHA256', 'bad')
                    else:
                        self.authority.write_text('\n'.join(line for line in self.authority.read_text().splitlines()
                                                            if not line.startswith('readonly ACTIONLINT_VERSION=')))
                    result = self.run_consumer(consumer, ACTIONLINT_VERSION='1.7.12', LINT_TOOL_VERSIONS_READY='1')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.log(), '')

    def test_no_migrations_does_not_download(self) -> None:
        result = self.run_consumer('squawk', NO_MIGRATIONS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log(), '')


if __name__ == '__main__':
    unittest.main()
