"""Execute image assembly with the real verified installers and offline artifacts."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / 'images/yueops-ci-toolchain'
INSTALLERS = ('ops-validation-gitleaks.sh', 'install-cosign.sh', 'install-verified-buildx.sh')


class VerifiedImageTools(unittest.TestCase):
    def capture(self, pattern, source, group=1):
        match = re.search(pattern, source)
        assert match is not None, pattern
        return match[group]

    def fixture(self, corrupt=''):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        policy = root / 'policy'
        scripts = policy / '.ci-policy/scripts'
        scripts.mkdir(parents=True)
        destination = root / 'installed'
        destination.mkdir()
        plugins = root / 'system-plugins'
        shims = root / 'shims'
        shims.mkdir()
        scratch = root / 'scratch'
        scratch.mkdir()
        artifacts = root / 'artifacts'
        artifacts.mkdir()
        shutil.copy(ROOT / 'scripts/ci-retry.sh', scripts)
        for name in INSTALLERS:
            source = (ROOT / 'scripts' / name).read_text()
            digest = self.capture(r'[0-9a-f]{64}', source, group=0)
            if name == 'ops-validation-gitleaks.sh':
                version = self.capture(r"release_url='https://github.com/gitleaks/gitleaks/releases/download/v([^/]+)/", source)
                artifact = artifacts / 'gitleaks'
                artifact.write_text(f'#!/bin/sh\necho {version}\n')
                artifact.chmod(0o755)
                archive = artifacts / 'gitleaks.tgz'
                with tarfile.open(archive, 'w:gz') as handle:
                    handle.add(artifact, arcname='gitleaks')
                artifact = archive
            else:
                variable = 'COSIGN_VERSION' if 'cosign' in name else 'BUILDX_VERSION'
                version = self.capture(rf"readonly {variable}='([^']+)'", source)
                artifact = artifacts / ('cosign' if 'cosign' in name else 'buildx')
                output = f'GitVersion: {version}' if 'cosign' in name else f'github.com/docker/buildx {version} fixture'
                artifact.write_text(f'#!/bin/sh\necho "{output}"\n')
                artifact.chmod(0o755)
            # Fixture copies change only trusted bytes/destination; real download,
            # checksum, extraction, version and ownership code remains executed.
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            source = source.replace(digest, '0' * 64 if name == corrupt else actual)
            (scripts / name).write_text(source.replace('/usr/local/bin', str(destination)))
        for name in ('install-verified-tools.sh', 'check-verified-tools.sh'):
            body = (IMAGE / name).read_text().replace('/opt/yueops-ci-tools', str(policy))
            body = body.replace('/usr/local/bin', str(destination)).replace('/usr/local/lib/docker/cli-plugins', str(plugins))
            (root / name).write_text(body)
        commands = {
            'uname': 'case "$1" in -s) echo Linux;; -m) echo x86_64;; *) exit 1;; esac',
            'sudo': '[ "$1" = -n ] && shift; exec "$@"',
            'curl': '''output=; url=
while [ "$#" -gt 0 ]; do
  case "$1" in -o|--output) output=$2; shift;; https://*) url=$1;; esac
  shift
done
case "$url" in
 */gitleaks/*) artifact=gitleaks.tgz;;
 */cosign/*) artifact=cosign;;
 */buildx/*) artifact=buildx;;
 *) exit 97;;
esac
cp "$ARTIFACTS/$artifact" "$output"''',
            'docker': '''[ "$1 $2" = 'buildx version' ] || exit 98
printf '%s|%s\\n' "$HOME" "${DOCKER_CONFIG:-}" >> "$LOOKUPS"
plugin="${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins/docker-buildx"
if [ ! -f "$plugin" ]; then
  [ "${NO_SYSTEM_PLUGIN:-}" != 1 ] || exit 96
  plugin="$SYSTEM_PLUGIN"
fi
exec "$plugin" version''',
        }
        for name, body in commands.items():
            path = shims / name
            path.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
            path.chmod(0o755)
        if os.uname().sysname == 'Darwin':
            for command in ('stat', 'sha256sum'):
                gnu = shutil.which('g' + command)
                assert gnu is not None, f'GNU {command} required for installer fixture'
                (shims / command).symlink_to(gnu)
        env = os.environ | {'PATH': os.pathsep.join((str(shims), str(destination), os.environ['PATH'])),
                            'TMPDIR': str(scratch) + '/', 'ARTIFACTS': str(artifacts),
                            'SYSTEM_PLUGIN': str(plugins / 'docker-buildx'), 'LOOKUPS': str(root / 'lookups')}
        env['DOCKER_CONFIG'] = str(root / 'ordinary-config')
        return root, destination, plugins, env

    def run_script(self, root, env, name):
        return subprocess.run(['bash', str(root / name)], env=env, capture_output=True, text=True, timeout=30)

    def test_verified_install_and_alternate_home_lookup_without_network(self):
        root, destination, plugins, env = self.fixture()
        installed = self.run_script(root, env, 'install-verified-tools.sh')
        self.assertEqual(installed.returncode, 0, installed.stderr)
        for binary in (destination / 'gitleaks', destination / 'cosign', plugins / 'docker-buildx'):
            self.assertEqual(binary.stat().st_mode & 0o777, 0o755)
        self.assertEqual((destination / 'gitleaks').stat().st_uid, os.getuid())
        self.assertEqual(list((root / 'scratch').iterdir()), [])
        checked = self.run_script(root, env, 'check-verified-tools.sh')
        self.assertEqual(checked.returncode, 0, checked.stderr)
        lookups = (root / 'lookups').read_text().splitlines()
        self.assertEqual(len(lookups), 3)  # Installer, ordinary HOME, replaced HOME.
        replaced_home, replaced_config = lookups[-1].split('|')
        self.assertEqual(replaced_home, replaced_config)
        self.assertFalse(Path(replaced_home).exists())
        self.assertEqual(list((root / 'scratch').iterdir()), [])
        # No user plugin is allowed to hide a missing system installation.
        absent = self.run_script(root, env | {'NO_SYSTEM_PLUGIN': '1'}, 'check-verified-tools.sh')
        self.assertNotEqual(absent.returncode, 0)
        stat = root / 'shims/stat'
        stat.unlink(missing_ok=True)
        stat.write_text(f'#!/bin/sh\necho {os.getuid() + 1}\n')
        stat.chmod(0o755)
        wrong_owner = self.run_script(root, env, 'check-verified-tools.sh')
        self.assertNotEqual(wrong_owner.returncode, 0)
        (destination / 'gitleaks').write_text('#!/bin/sh\necho wrong-version\n')
        wrong = self.run_script(root, env, 'check-verified-tools.sh')
        self.assertNotEqual(wrong.returncode, 0)

    def test_bad_artifacts_never_promote_tool_outputs_and_clean_scratch(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer):
                root, destination, plugins, env = self.fixture(corrupt=installer)
                result = self.run_script(root, env, 'install-verified-tools.sh')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAILED', result.stdout)
                self.assertFalse((destination / 'cosign').exists())
                self.assertFalse((plugins / 'docker-buildx').exists())
                if installer == 'ops-validation-gitleaks.sh':
                    self.assertFalse((destination / 'gitleaks').exists())
                self.assertEqual(list((root / 'scratch').iterdir()), [])

    def test_context_is_explicit_and_both_builders_use_the_same_recipe(self):
        recipe = (IMAGE / 'Dockerfile').read_text()
        sources = set()
        for line in recipe.splitlines():
            if line.startswith('COPY '):
                fields = line.split()[1:-1]
                self.assertTrue(all('*' not in item and item != '.' and not item.startswith('--') for item in fields))
                sources.update(fields)
        expected = {f'scripts/{name}' for name in (*INSTALLERS, 'ci-retry.sh')} | {
            f'images/yueops-ci-toolchain/{name}' for name in ('selfcheck.sh', 'docker-hostpath.sh',
                                                            'install-verified-tools.sh', 'check-verified-tools.sh')}
        self.assertEqual(sources, expected)
        ignores = (IMAGE / 'Dockerfile.dockerignore').read_text().splitlines()
        self.assertIn('**', ignores)
        allowed = {line[1:] for line in ignores if line.startswith('!') and not line.endswith('/')}
        self.assertEqual(allowed, expected | {'images/yueops-ci-toolchain/Dockerfile',
                                            'images/yueops-ci-toolchain/Dockerfile.dockerignore'})
        self.assertLess(recipe.index('USER runner'), recipe.index('RUN bash /opt/yueops-ci-tools/install-verified-tools.sh'))
        self.assertIn('yueops-ci-check-verified-tools', (IMAGE / 'selfcheck.sh').read_text())
        for file, job in (('build.yml', 'toolchain-image'), ('ci-toolchain.yml', 'image')):
            workflow = yaml.safe_load((ROOT / '.github/workflows' / file).read_text())
            build = next(step for step in workflow['jobs'][job]['steps'] if step.get('id') == 'image')
            self.assertEqual(build['with']['context'], '.')
            self.assertEqual(build['with']['file'], 'images/yueops-ci-toolchain/Dockerfile')
        trigger = workflow.get('on', workflow.get(True))
        for source in (f'scripts/{name}' for name in (*INSTALLERS, 'ci-retry.sh')):
            self.assertIn(source, trigger['push']['paths'])
        for helper in ('install-verified-tools.sh', 'check-verified-tools.sh'):
            body = (IMAGE / helper).read_text()
            self.assertNotRegex(body, r'[0-9a-f]{64}')
            self.assertNotRegex(body, r'v?\d+\.\d+\.\d+')
