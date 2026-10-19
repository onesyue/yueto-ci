"""Execute the native installer boundary and its fail-closed input contract."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeNginxToolchain(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.log = self.root / 'calls.jsonl'
        self.policy = self.root / 'policy-rc.d'
        self.policy.write_text('#!/bin/sh\nexit 102\n')
        self.policy.chmod(0o740)
        self.original_policy = self.policy.read_bytes()
        self.manifest = json.loads((ROOT / 'scripts/native-nginx-toolchain.json').read_text())
        self.payload = b'disposable package fixture, never installed by dpkg\n'
        for arch in ('amd64', 'arm64'):
            self.manifest['packages'][arch]['sha256'] = hashlib.sha256(self.payload).hexdigest()
            (self.cache / f'nginx_1.30.5-1~noble_{arch}.deb').write_bytes(self.payload)
        self.write_manifest()
        source = (ROOT / 'scripts/install-native-nginx.sh').read_text()
        # Redirect only the two absolute OS-owned paths into this disposable lab.
        # The actual package/NGINX acceptance runs separately in Linux UID0.
        assert source.count('/usr/sbin/policy-rc.d') == 1
        assert source.count('/usr/sbin/nginx') == 2
        assert source.count('/etc/os-release') == 1
        source = source.replace('/etc/os-release', str(self.root/'os-release'))
        source = source.replace('/usr/sbin/policy-rc.d', str(self.policy))
        source = source.replace('/usr/sbin/nginx', str(self.bin / 'nginx'))
        self.script = self.root / 'install-native-nginx.sh'
        self.script.write_text(source)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        LAB=str(self.root), ARCH='arm64')
        dispatcher = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
root=pathlib.Path(os.environ['LAB'])
with (root/'calls.jsonl').open('a') as out:
 out.write(json.dumps([name,*args])+'\\n')
if name=='uname': print('Linux')
elif name=='id': print(os.getenv('UID_REPLY','0'))
elif name=='lsb_release': print(os.getenv('DISTRO','Ubuntu') if args==['-is'] else os.getenv('CODENAME','noble'))
elif name=='dpkg': print(os.environ['ARCH'])
elif name=='dpkg-deb':
 print({'Package':'nginx','Version':os.getenv('DEB_VERSION','1.30.5-1~noble'),'Architecture':os.getenv('DEB_ARCH',os.environ['ARCH'])}[args[-1]])
elif name=='dpkg-query':
 if args[-1]=='libnginx-mod-stream':
  if os.getenv('STREAM_INSTALLED')=='1': print('install ok installed')
  else: sys.exit(1)
 else: print(os.getenv('INSTALLED_VERSION','1.30.5-1~noble'))
elif name=='apt-get':
 assert (root/'policy-rc.d').read_text()=='#!/bin/sh\\nexit 101\\n'
 if args[0]==os.getenv('APT_FAIL'): sys.exit(21)
elif name=='curl':
 if os.getenv('CURL_FAIL')=='1': sys.exit(22)
 pathlib.Path(args[args.index('--output')+1]).write_bytes(b'disposable package fixture, never installed by dpkg\\n')
elif name=='nginx':
 if args==['-v']: print('nginx version: nginx/'+os.getenv('BINARY_VERSION','1.30.5'),file=sys.stderr)
 elif args==['-V']:
  flags='--with-stream --with-stream_ssl_module --with-stream_ssl_preread_module --with-http_ssl_module'
  if os.getenv('MISSING_STREAM')=='1': flags=flags.replace('--with-stream ', '--with-stream=dynamic ')
  print('configure arguments: '+flags)
 else:
  text=pathlib.Path(args[args.index('-c')+1]).read_text()
  assert 'keepalive_min_timeout 5s;' in text and 'stream {}' in text
  if os.getenv('CONFIG_FAIL')=='1': sys.exit(23)
else: sys.exit(24)
'''
        for command in ('uname','id','lsb_release','dpkg','dpkg-deb','dpkg-query','apt-get','curl','nginx'):
            path = self.bin / command
            path.write_text(dispatcher)
            path.chmod(0o755)

    def write_manifest(self):
        (self.root / 'native-nginx-toolchain.json').write_text(json.dumps(self.manifest))

    def execute(self, *, offline=True, changes=None):
        changes = changes or {}
        (self.root/'os-release').write_text('ID='+changes.get('DISTRO','ubuntu')+'\nVERSION_CODENAME='+changes.get('CODENAME','noble')+'\n')
        env = dict(self.env, **changes)
        args = ['bash', str(self.script)]
        if offline:
            args += ['--package-cache', str(self.cache)]
        return subprocess.run(args, env=env, text=True, capture_output=True, timeout=30)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_restored(self):
        self.assertEqual(self.policy.read_bytes(), self.original_policy)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o740)

    def test_offline_installs_both_architectures_and_restores_policy(self):
        for architecture in ('arm64','amd64'):
            with self.subTest(architecture=architecture):
                result = self.execute(changes={'ARCH':architecture,'STREAM_INSTALLED':'1'})
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                self.assertNotIn('curl', [row[0] for row in calls])
                remove = next(i for i,row in enumerate(calls) if row[:2]==['apt-get','remove'])
                install = next(i for i,row in enumerate(calls) if row[:2]==['apt-get','install'])
                self.assertLess(remove, install)
                self.assertIn('logrotate', calls[install])
                self.assertTrue(any(row[:2]==['nginx','-t'] for row in calls))
                self.assertIn('NATIVE_NGINX_TOOLCHAIN_READY', result.stdout)
                self.assert_restored()
                self.log.unlink()

    def test_online_download_runs_hash_and_package_validation_before_apt(self):
        result = self.execute(offline=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [row[0] for row in self.calls()]
        self.assertLess(names.index('curl'), names.index('dpkg-deb'))
        self.assertLess(names.index('dpkg-deb'), names.index('apt-get'))
        self.assert_restored()

    def test_invalid_inputs_never_reach_package_transaction(self):
        cases = [{'ARCH':'riscv64'},{'DISTRO':'Debian'},{'CODENAME':'jammy'},
                 {'UID_REPLY':'1001'},{'DEB_ARCH':'amd64'},{'DEB_VERSION':'1.30.6-1~noble'}]
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.execute(changes=changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(row[0]=='apt-get' for row in self.calls()))
                self.assert_restored()
                if self.log.exists(): self.log.unlink()

    def test_wrong_hash_never_reaches_package_parser_or_apt(self):
        (self.cache/'nginx_1.30.5-1~noble_arm64.deb').write_bytes(b'tampered')
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0] in ('dpkg-deb','apt-get') for row in self.calls()))
        self.assert_restored()

    def test_missing_offline_package_does_not_download(self):
        (self.cache/'nginx_1.30.5-1~noble_arm64.deb').unlink()
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0] in ('curl','apt-get') for row in self.calls()))

    def test_download_failure_cannot_install(self):
        result = self.execute(offline=False, changes={'CURL_FAIL':'1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0]=='apt-get' for row in self.calls()))

    def test_install_and_actual_consumer_failures_cannot_report_ready(self):
        cases = [{'APT_FAIL':'update'},{'APT_FAIL':'remove','STREAM_INSTALLED':'1'},
                 {'APT_FAIL':'install'},{'INSTALLED_VERSION':'1.24.0'},
                 {'BINARY_VERSION':'1.24.0'},{'MISSING_STREAM':'1'},{'CONFIG_FAIL':'1'}]
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.execute(changes=changes)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('NATIVE_NGINX_TOOLCHAIN_READY', result.stdout)
                self.assert_restored()

    def test_shadowing_binary_in_path_is_refused(self):
        shadow = self.root/'shadow'
        shadow.mkdir()
        (shadow/'nginx').write_text((self.bin/'nginx').read_text())
        (shadow/'nginx').chmod(0o755)
        result = self.execute(changes={'PATH':str(shadow)+os.pathsep+self.env['PATH']})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PATH selects an unexpected nginx binary', result.stderr)
        self.assertNotIn('NATIVE_NGINX_TOOLCHAIN_READY', result.stdout)
        self.assert_restored()

    def test_missing_manifest_is_a_refusal_before_apt(self):
        (self.root/'native-nginx-toolchain.json').unlink()
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0]=='apt-get' for row in self.calls()))

    def test_absent_policy_is_removed_on_failure(self):
        self.policy.unlink()
        result = self.execute(changes={'APT_FAIL':'install'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.policy.exists())

    def test_symlinked_policy_is_refused_before_apt(self):
        self.policy.unlink()
        target = self.root/'target'
        target.write_text('unchanged')
        self.policy.symlink_to(target)
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), 'unchanged')
        self.assertFalse(any(row[0]=='apt-get' for row in self.calls()))

    def test_actual_workflow_invokes_immutable_policy_installer(self):
        workflow = (ROOT/'.github/workflows/build.yml').read_text()
        start = workflow.index('      - name: Install native YueOps NGINX test toolchain\n')
        step = workflow[start:workflow.index('\n      - name:',start+1)]
        self.assertIn("if: matrix.validation == 'yueops'", step)
        self.assertIn('sudo -n env PATH="$PATH" bash .ci-policy/scripts/install-native-nginx.sh', step)
        self.assertNotIn('libnginx-mod-stream', step)
        self.assertIn('ref: ${{ github.sha }}\n          path: .ci-policy', workflow)
        self.assertIn('sudo -n env PATH="$PATH" TZ=UTC "$PWD/.venv/bin/python" scripts/run-native-nginx-tests.py',workflow)

    def test_canonical_inputs_have_two_official_exact_version_pins(self):
        manifest = json.loads((ROOT/'scripts/native-nginx-toolchain.json').read_text())
        self.assertEqual(set(manifest['packages']), {'amd64','arm64'})
        self.assertEqual(manifest['package_version'], '1.30.5-1~noble')
        for arch,package in manifest['packages'].items():
            self.assertEqual(package['url'], 'https://nginx.org/packages/ubuntu/pool/nginx/n/nginx/nginx_1.30.5-1~noble_'+arch+'.deb')
            self.assertRegex(package['sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
