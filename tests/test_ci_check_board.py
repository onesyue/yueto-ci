"""Board defaults use the existing signed snapshot API, with no pin fallback."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('board_default', ROOT / 'scripts/ci_check_board.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BoardContext(unittest.TestCase):
    def test_signed_snapshot_is_consumed_and_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            path = root / 'scripts/release-yaml.py'
            path.write_text('''
import os
from pathlib import Path
ROOT = Path(os.environ['YUETO_ROOT'])
assert ROOT == Path(__file__).resolve().parents[1]
def verified_desired():
    return {"verified": True}, b"snapshot"
def desired_revision(record, target):
    assert record == {"verified": True} and target == "yueboard"
    return "a" * 40
def assert_desired_unchanged(snapshot):
    assert snapshot == b"snapshot"
''')
            with patch.dict(os.environ, {'YUETO_ROOT': '/unrelated/root'}):
                self.assertEqual(MODULE.desired_board(root), 'a' * 40)
                self.assertEqual(os.environ['YUETO_ROOT'], '/unrelated/root')
            path.write_text(path.read_text().replace('assert snapshot == b"snapshot"',
                                                    'raise ValueError("snapshot changed")'))
            with self.assertRaisesRegex(ValueError, 'snapshot changed'):
                MODULE.desired_board(root)
            path.write_text('def verified_desired(): raise ValueError("signature rejected")\n')
            with self.assertRaisesRegex(ValueError, 'signature rejected'):
                MODULE.desired_board(root)

    def test_no_root_reader_fails_without_using_central_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'YUETO_ROOT'):
                MODULE.desired_board(Path(directory))

    def test_schema_input_is_owned_by_selected_board_and_missing_structure_rejects(self):
        spec = importlib.util.spec_from_file_location('native_board_context',
                                                     ROOT / 'scripts/validate-native-node-contract.py')
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory)
            (board / 'schema-floor.txt').write_text('42\n')
            fixture = board / 'test/fixtures/schema.sql'
            fixture.parent.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                native.validate_board_schema_input(board)
            fixture.write_text('CREATE TABLE example (id bigint PRIMARY KEY);\n')
            native.validate_board_schema_input(board)
            fixture.write_text('')
            with self.assertRaises(RuntimeError):
                native.validate_board_schema_input(board)
            fixture.unlink()
            fixture.symlink_to(board / 'schema-floor.txt')
            with self.assertRaises(RuntimeError):
                native.validate_board_schema_input(board)
            (board / 'schema-floor.txt').write_text('0\n')
            with self.assertRaisesRegex(RuntimeError, 'positive integer'):
                native.validate_board_schema_input(board)

    def test_ambiguous_promoted_board_manifest_fails_before_reading_a_child(self):
        spec = importlib.util.spec_from_file_location('fingerprint', ROOT / 'scripts/input-fingerprint.py')
        registry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(registry)
        candidates = [{'platform': {'architecture': 'amd64', 'os': 'linux'}, 'digest': 'sha256:' + c*64}
                      for c in ('a', 'b')]
        index = io.BytesIO(json.dumps({'manifests': candidates}).encode())
        index.headers = {'Docker-Content-Digest': 'sha256:' + 'c'*64}
        with patch('urllib.request.urlopen', side_effect=[io.BytesIO(b'{"token":"fixture"}'), index]) as read:
            with self.assertRaisesRegex(registry.Unknown, 'ambiguous'):
                registry.ghcr_latest('yueboard', 'fixture', 'fixture')
        self.assertEqual(read.call_count, 2)

    def test_real_workflow_resolves_contract_and_keeps_board_preflight_on_promoted_revision(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertIn('YUEBOARD_CONTRACT_REF: ${{ github.event.inputs.yueboard_contract_ref', text)
        self.assertIn('promoted_board_ref: ${{ steps.plan.outputs.promoted_board_ref }}', text)
        self.assertIn('PROMOTED_BOARD_REF: ${{ needs.plan.outputs.promoted_board_ref }}', text)
        self.assertIn('echo "promoted_board_ref=$promoted_board_ref"', text)
        start = text.index('          promoted_board_ref=""')
        end = text.index('          if [ "$validation_only" = true ]; then', start)
        shell = text[start:end] + 'printf "%s|%s" "$yueboard_contract_ref" "$promoted_board_ref"'
        promoted, explicit = 'a'*40, 'b'*40
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / 'scripts'
            scripts.mkdir()
            shutil.copy(ROOT / 'scripts/validate-native-node-contract.py', scripts)
            lib = scripts / "lib"
            lib.mkdir()
            (lib / "ci_constants.py").write_bytes((ROOT / "scripts/lib/ci_constants.py").read_bytes())
            (scripts / 'input-fingerprint.py').write_text(
                'import os\nclass Unknown(Exception): pass\n'
                'def ghcr_latest(service, user, password):\n'
                '    return "fixture", os.environ["FIXTURE_PROMOTED"]\n')
            for targets, override, available, expected in [
                (['yueops'], '', promoted, promoted + '|'),
                (['yue-node'], '', promoted, promoted + '|'),
                (['yueops'], explicit, '', explicit + '|'),
                (['yueops'], 'master', promoted, None),
                (['yue-node'], '', '', None),
                (['yueops'], '', promoted + '\n' + explicit, None),
                (['yueboard'], '', promoted, promoted + '|' + promoted),
                (['yueboard', 'yueops'], explicit, promoted, explicit + '|' + promoted),
                (['yueboard'], explicit, '', None),
                (['yuelink'], '', '', '|'),
            ]:
                with self.subTest(targets=targets, override=override, available=available):
                    env = os.environ | {'target_plan': json.dumps({'validation_matrix': [
                        {'validation': target} for target in targets]}), 'YUEBOARD_CONTRACT_REF': override,
                        'FIXTURE_PROMOTED': available, 'GHCR_USER': 'fixture', 'GHCR_PASSWORD': 'fixture'}
                    result = subprocess.run(['bash', '-euc', shell], cwd=directory, env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, expected is not None, result.stderr)
                    self.assertEqual(result.stdout, expected or '')
