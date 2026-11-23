"""Ubuntu archive fallback before privileged Playwright installs. No network."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/lib/apt-mirror-fallback.sh'
NODE = ROOT / 'scripts/ops-validation-node.sh'
BOARD = ROOT / 'scripts/board-validation.sh'
NOTICE = (
    '::notice::Ubuntu archive mirror unreachable; '
    'apt sources now use azure.archive.ubuntu.com'
)
PROBE = '-fsS --max-time 10 -o /dev/null http://archive.ubuntu.com/ubuntu/dists/{codename}/InRelease'
UPDATE = '-o Acquire::Retries=3 -o Acquire::http::Timeout=20 update'

LIST_BEFORE = """\
deb http://archive.ubuntu.com/ubuntu noble main restricted
deb https://security.ubuntu.com/ubuntu noble-security main
deb http://azure.archive.ubuntu.com/ubuntu noble main
deb mirror+http://archive.ubuntu.com/ubuntu noble universe
deb http://ppa.launchpad.net/example/ppa/ubuntu noble main
deb http://ports.ubuntu.com/ubuntu-ports noble main
deb http://notsecurity.ubuntu.com/ubuntu noble main
deb http://security.ubuntu.com.evil/ubuntu noble main
deb [arch=amd64] https://archive.ubuntu.com/ubuntu noble multiverse
# archive.ubuntu.com
"""

LIST_AFTER = """\
deb http://azure.archive.ubuntu.com/ubuntu noble main restricted
deb https://azure.archive.ubuntu.com/ubuntu noble-security main
deb http://azure.archive.ubuntu.com/ubuntu noble main
deb mirror+http://azure.archive.ubuntu.com/ubuntu noble universe
deb http://ppa.launchpad.net/example/ppa/ubuntu noble main
deb http://ports.ubuntu.com/ubuntu-ports noble main
deb http://notsecurity.ubuntu.com/ubuntu noble main
deb http://security.ubuntu.com.evil/ubuntu noble main
deb [arch=amd64] https://azure.archive.ubuntu.com/ubuntu noble multiverse
# azure.archive.ubuntu.com
"""

SOURCES_BEFORE = """\
Types: deb
URIs: http://archive.ubuntu.com/ubuntu/ http://security.ubuntu.com/ubuntu/
Suites: noble noble-security
Components: main universe
URIs: https://deb.nodesource.com/node_20.x
"""

SOURCES_AFTER = """\
Types: deb
URIs: http://azure.archive.ubuntu.com/ubuntu/ http://azure.archive.ubuntu.com/ubuntu/
Suites: noble noble-security
Components: main universe
URIs: https://deb.nodesource.com/node_20.x
"""

UNTOUCHED = 'deb http://archive.ubuntu.com/ubuntu noble main\n'
INSTALL_WITH_DEPS = 'pnpm --dir site exec playwright install --with-deps chromium'
INSTALL_PLAIN = 'pnpm --dir site exec playwright install chromium'
SITE_TEST = 'pnpm --dir site test'


class AptMirrorFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.tools = self.root / 'tools'
        self.sources = self.root / 'apt'
        self.bin.mkdir()
        self.tools.mkdir()
        self.order_log = self.root / 'order.log'
        self.curl_log = self.root / 'curl.log'
        self.apt_log = self.root / 'apt.log'
        self.sudo_log = self.root / 'sudo.log'
        self.os_release = self.root / 'os-release'
        self.write_os('jammy')
        self.write_sources()
        self.executable(self.bin / 'curl', 'printf "%s\\n" "POISON ${0##*/} $*" >> "$ORDER_LOG"\nexit 97\n')
        self.executable(self.bin / 'apt-get', 'printf "%s\\n" "POISON ${0##*/} $*" >> "$ORDER_LOG"\nexit 97\n')
        self.executable(self.bin / 'id', 'printf "%s\\n" "${FAKE_UID:?}"\n')
        self.executable(self.bin / 'sudo', """\
printf '%s\\n' "$*" >> "$SUDO_LOG"
if [ "$1" = -n ]; then shift; fi
if [ "${SUDO_EXIT:-0}" != 0 ]; then exit "$SUDO_EXIT"; fi
exec "$@"
""")
        self.executable(self.bin / 'npm', 'printf "%s\\n" "npm $*" >> "$ORDER_LOG"\nexit 0\n')
        self.executable(self.bin / 'corepack', 'printf "%s\\n" "corepack $*" >> "$ORDER_LOG"\nexit 0\n')
        self.executable(self.bin / 'node', 'printf "%s\\n" "node $*" >> "$ORDER_LOG"\nprintf "%s\\n" "pnpm@9.15.0"\nexit 0\n')
        self.executable(self.bin / 'pnpm', """\
printf '%s\\n' "pnpm $*" >> "$ORDER_LOG"
case "$*" in
  *"playwright install"*) exit "${INSTALL_EXIT:-0}" ;;
esac
exit 0
""")
        self.executable(self.tools / 'curl', """\
printf '%s\\n' "curl $*" >> "$ORDER_LOG"
printf '%s\\n' "$*" >> "$CURL_LOG"
case "$*" in *"https://${REACHABLE_HOST:-invalid}/"*) exit 0;; esac
exit "${CURL_EXIT:-1}"
""")
        self.executable(self.tools / 'apt-get', """\
printf '%s\\n' "apt-get $*" >> "$ORDER_LOG"
printf '%s\\n' "$*" >> "$APT_LOG"
exit "${APT_EXIT:-0}"
""")

    def executable(self, path, body):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def write_os(self, codename):
        self.os_release.write_text(f'NAME="Ubuntu"\nVERSION_CODENAME={codename}\n')

    def write_sources(self):
        listed = self.sources / 'sources.list.d'
        if self.sources.exists() or self.sources.is_symlink():
            if self.sources.is_symlink():
                self.sources.unlink()
            else:
                for path in sorted(self.sources.rglob('*'), reverse=True):
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                self.sources.rmdir()
        listed.mkdir(parents=True)
        (self.sources / 'sources.list').write_text(LIST_BEFORE)
        (listed / 'ubuntu.sources').write_text(SOURCES_BEFORE)
        (listed / 'nodesource.list').write_text('deb https://deb.nodesource.com/node_20.x nodistro main\n')
        (listed / 'kept.list.bak').write_text(UNTOUCHED)
        (listed / 'kept.list.disabled').write_text(UNTOUCHED)
        (listed / 'kept.sources.bak').write_text(UNTOUCHED)
        outside = self.root / 'outside.list'
        outside.write_text(UNTOUCHED)
        (listed / 'link.list').symlink_to(outside)

    def environment(self, **extra):
        env = {
            'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
            'TMPDIR': str(self.root),
            'YUETO_APT_CURL': str(self.tools / 'curl'),
            'YUETO_APT_GET': str(self.tools / 'apt-get'),
            'YUETO_APT_OS_RELEASE': str(self.os_release),
            'YUETO_APT_SOURCES_DIR': str(self.sources),
            'ORDER_LOG': str(self.order_log),
            'CURL_LOG': str(self.curl_log),
            'APT_LOG': str(self.apt_log),
            'SUDO_LOG': str(self.sudo_log),
            'FAKE_UID': '0',
            'CURL_EXIT': '1',
            'SUDO_EXIT': '0',
            'APT_EXIT': '0',
            'INSTALL_EXIT': '0',
        }
        env.update(extra)
        return env

    def clear_logs(self):
        for path in (self.order_log, self.curl_log, self.apt_log, self.sudo_log):
            path.unlink(missing_ok=True)

    def run_helper(self, **extra):
        self.clear_logs()
        return subprocess.run(
            ['bash', '-c', 'set -euo pipefail; . "$1"', 'apt-mirror-fallback', str(HELPER)],
            env=self.environment(**extra),
            capture_output=True,
            text=True,
        )

    def text(self, path):
        return path.read_text() if path.exists() else ''

    def assert_unchanged_outside_ubuntu_archives(self):
        listed = self.sources / 'sources.list.d'
        self.assertEqual((listed / 'nodesource.list').read_text(),
                         'deb https://deb.nodesource.com/node_20.x nodistro main\n')
        self.assertEqual((listed / 'kept.list.bak').read_text(), UNTOUCHED)
        self.assertEqual((listed / 'kept.list.disabled').read_text(), UNTOUCHED)
        self.assertEqual((listed / 'kept.sources.bak').read_text(), UNTOUCHED)
        self.assertEqual((self.root / 'outside.list').read_text(), UNTOUCHED)
        self.assertTrue((listed / 'link.list').is_symlink())

    def test_callers_source_helper_before_playwright_install(self):
        checks = (
            (NODE, 'pnpm --dir site exec playwright install'),
            (BOARD, 'pnpm --dir web exec playwright install'),
            (BOARD, 'pnpm --dir test/e2e exec playwright install'),
            (BOARD, 'pnpm --dir test/a11y exec playwright-core install'),
        )
        for path, marker in checks:
            text = path.read_text()
            index = text.index(marker)
            window = text[max(0, index - 900):index]
            source = 'cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/apt-mirror-fallback.sh'
            self.assertIn(source, window, marker)
            self.assertIn('deps=(--with-deps)', window, marker)
            privilege = window.rindex('if [ "$(id -u)" -eq 0 ]')
            sourced = window.rindex(source)
            closed = window.rindex('fi')
            self.assertLess(privilege, sourced, marker)
            self.assertLess(sourced, closed, marker)
            install = text[index:text.index('\n', index)]
            self.assertIn('"${deps[@]}"', install, marker)
        self.assertEqual(NODE.read_text().count('lib/apt-mirror-fallback.sh'), 2)
        self.assertEqual(BOARD.read_text().count('lib/apt-mirror-fallback.sh'), 6)

    def test_probe_success_is_noop(self):
        before = (self.sources / 'sources.list').read_text()
        result = self.run_helper(CURL_EXIT='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('::notice::', result.stdout)
        self.assertEqual(result.stdout, '')
        self.assertEqual((self.sources / 'sources.list').read_text(), before)
        self.assertEqual((self.sources / 'sources.list.d' / 'ubuntu.sources').read_text(), SOURCES_BEFORE)
        self.assert_unchanged_outside_ubuntu_archives()
        self.assertEqual(self.text(self.curl_log), PROBE.format(codename='jammy') + '\n')
        self.assertFalse(self.apt_log.exists())
        self.assertFalse(self.sudo_log.exists())
        self.assertNotIn('POISON', self.text(self.order_log))

    def test_probe_failure_rewrites_only_ubuntu_archive_hosts(self):
        for uid, label in (('0', 'root'), ('1001', 'sudo')):
            with self.subTest(label=label):
                self.write_sources()
                result = self.run_helper(FAKE_UID=uid)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, NOTICE + '\n')
                self.assertEqual((self.sources / 'sources.list').read_text(), LIST_AFTER)
                self.assertEqual((self.sources / 'sources.list.d' / 'ubuntu.sources').read_text(), SOURCES_AFTER)
                self.assert_unchanged_outside_ubuntu_archives()
                rewritten = (self.sources / 'sources.list').read_text()
                self.assertNotIn('azure.archive.azure.archive', rewritten)
                self.assertIn('https://azure.archive.ubuntu.com', rewritten)
                self.assertNotIn('https://security.ubuntu.com', rewritten)
                self.assertNotIn('http://archive.ubuntu.com', rewritten)
                http = PROBE.format(codename='jammy')
                https = http.replace('http:', 'https:')
                self.assertEqual(self.text(self.curl_log).splitlines(),
                                 [http, https, https.replace('//archive.', '//azure.archive.')])
                self.assertEqual(self.text(self.apt_log), UPDATE + '\n')
                self.assertNotIn('POISON', self.text(self.order_log))
                sudo = self.text(self.sudo_log)
                if uid == '0':
                    self.assertNotIn('tee', sudo)
                    self.assertNotIn('apt-get', sudo)
                else:
                    self.assertIn('tee ', sudo)
                    self.assertIn('Acquire::Retries=3', sudo)
                    self.assertIn('Acquire::http::Timeout=20', sudo)

    def test_port_80_outage_uses_a_reachable_https_archive(self):
        for host in ('archive.ubuntu.com', 'azure.archive.ubuntu.com'):
            with self.subTest(host=host):
                self.write_sources()
                result = self.run_helper(REACHABLE_HOST=host)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'https://{host}', result.stdout)
                sources = (self.sources / 'sources.list.d' / 'ubuntu.sources').read_text()
                self.assertIn(f'URIs: https://{host}/ubuntu/ https://{host}/ubuntu/', sources)
                self.assertNotIn('http://archive.ubuntu.com', sources)
                self.assertEqual(self.text(self.apt_log), UPDATE + '\n')
                self.assert_unchanged_outside_ubuntu_archives()

    def test_unprivileged_does_not_probe_or_rewrite(self):
        before = (self.sources / 'sources.list').read_text()
        result = self.run_helper(FAKE_UID='1001', SUDO_EXIT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual((self.sources / 'sources.list').read_text(), before)
        self.assertFalse(self.curl_log.exists())
        self.assertFalse(self.apt_log.exists())
        self.assertNotIn('POISON', self.text(self.order_log))

    def test_rejects_missing_or_unsafe_codename_before_probe(self):
        cases = (
            ('missing', None, 'OS release file is missing'),
            ('empty', 'VERSION_CODENAME=\n', 'unsupported VERSION_CODENAME'),
            ('capital', 'VERSION_CODENAME="Noble"\n', 'unsupported VERSION_CODENAME'),
            ('digits', 'VERSION_CODENAME=24\n', 'unsupported VERSION_CODENAME'),
            ('separator', 'VERSION_CODENAME=noble-updates\n', 'unsupported VERSION_CODENAME'),
        )
        for label, body, message in cases:
            with self.subTest(label=label):
                self.write_sources()
                if body is None:
                    self.os_release.unlink()
                else:
                    self.os_release.write_text(body)
                before = (self.sources / 'sources.list').read_text()
                result = self.run_helper()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn('::notice::', result.stdout)
                self.assertEqual((self.sources / 'sources.list').read_text(), before)
                self.assertFalse(self.curl_log.exists())
                self.assertFalse(self.apt_log.exists())
        self.write_os('jammy')

    def test_skips_symlink_sources_and_still_updates_when_nothing_changes(self):
        real = self.root / 'real-apt'
        real.mkdir()
        (real / 'sources.list').write_text(LIST_BEFORE)
        linked = self.root / 'linked-apt'
        linked.symlink_to(real)
        result = self.run_helper(YUETO_APT_SOURCES_DIR=str(linked))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('apt sources directory is missing', result.stderr)
        self.assertEqual((real / 'sources.list').read_text(), LIST_BEFORE)
        self.assertNotIn('::notice::', result.stdout)
        self.assertFalse(self.apt_log.exists())

        self.write_sources()
        only = 'deb http://ppa.launchpad.net/example/ppa/ubuntu noble main\n'
        (self.sources / 'sources.list').write_text(only)
        for extra in (self.sources / 'sources.list.d').iterdir():
            extra.unlink()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual((self.sources / 'sources.list').read_text(), only)
        self.assertEqual(self.text(self.apt_log), UPDATE + '\n')

    def test_ops_validation_node_orders_fallback_before_playwright(self):
        modes = (
            ('root-down', {'FAKE_UID': '0', 'CURL_EXIT': '1'}, True, True),
            ('root-up', {'FAKE_UID': '0', 'CURL_EXIT': '0'}, True, False),
            ('user', {'FAKE_UID': '1001', 'SUDO_EXIT': '1', 'CURL_EXIT': '1'}, False, False),
            ('sudo-down', {'FAKE_UID': '1001', 'CURL_EXIT': '1'}, True, True),
        )
        for label, extra, with_deps, rewrite in modes:
            with self.subTest(label=label):
                self.write_os('noble')
                self.write_sources()
                before = (self.sources / 'sources.list').read_text()
                self.clear_logs()
                result = subprocess.run(
                    ['bash', str(NODE)],
                    cwd=self.root,
                    env=self.environment(**extra),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = self.text(self.order_log).splitlines()
                install = INSTALL_WITH_DEPS if with_deps else INSTALL_PLAIN
                self.assertIn(install, lines)
                self.assertLess(lines.index(install), lines.index(SITE_TEST))
                self.assertNotIn('POISON', lines)
                if rewrite:
                    self.assertEqual(result.stdout, NOTICE + '\n')
                    self.assertEqual((self.sources / 'sources.list').read_text(), LIST_AFTER)
                    self.assertLess(lines.index('curl ' + PROBE.format(codename='noble')), lines.index('apt-get ' + UPDATE))
                    self.assertLess(lines.index('apt-get ' + UPDATE), lines.index(install))
                else:
                    self.assertNotIn('::notice::', result.stdout)
                    self.assertEqual((self.sources / 'sources.list').read_text(), before)
                    self.assertNotIn('apt-get ' + UPDATE, lines)
                    if with_deps:
                        self.assertLess(lines.index('curl ' + PROBE.format(codename='noble')), lines.index(install))
                    else:
                        self.assertFalse(any(line.startswith('curl ') for line in lines))

        self.write_os('noble')
        self.write_sources()
        self.clear_logs()
        failed = subprocess.run(
            ['bash', str(NODE)],
            cwd=self.root,
            env=self.environment(FAKE_UID='0', CURL_EXIT='1', INSTALL_EXIT='17'),
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed.returncode, 17)
        failed_lines = self.text(self.order_log).splitlines()
        self.assertIn(INSTALL_WITH_DEPS, failed_lines)
        self.assertNotIn(SITE_TEST, failed_lines)

        isolated = self.root / 'isolated'
        isolated.mkdir()
        (isolated / 'ops-validation-node.sh').write_text(NODE.read_text())
        self.clear_logs()
        missing = subprocess.run(
            ['bash', str(isolated / 'ops-validation-node.sh')],
            cwd=self.root,
            env=self.environment(FAKE_UID='0', CURL_EXIT='1'),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('apt-mirror-fallback.sh', missing.stderr)
        self.assertNotIn(SITE_TEST, self.text(self.order_log).splitlines())
        self.clear_logs()
        unprivileged = subprocess.run(
            ['bash', str(isolated / 'ops-validation-node.sh')],
            cwd=self.root,
            env=self.environment(FAKE_UID='1001', SUDO_EXIT='1'),
            capture_output=True,
            text=True,
        )
        self.assertEqual(unprivileged.returncode, 0, unprivileged.stderr)
        plain = self.text(self.order_log).splitlines()
        self.assertIn(INSTALL_PLAIN, plain)
        self.assertLess(plain.index(INSTALL_PLAIN), plain.index(SITE_TEST))
        self.assertFalse(any(line.startswith('curl ') for line in plain))


if __name__ == '__main__':
    unittest.main()
