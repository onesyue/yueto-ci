"""Board defaults use the existing signed snapshot API, with no pin fallback."""
import importlib.util
import os
from pathlib import Path
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

    def test_real_workflow_requires_explicit_ops_context_but_keeps_board_publication_pin(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertIn("matrix.validation == 'yueops' && needs.plan.outputs.yueboard_contract_ref || needs.plan.outputs.yueboard_policy_pin", text)
        self.assertIn('YUEBOARD_CONTRACT_REF: ${{ github.event.inputs.yueboard_contract_ref', text)
        start = text.index("          if jq -e 'any(.validation_matrix[]; .validation == \"yueops\")'")
        end = text.index('          if [ "$validation_only" = true ]; then', start)
        shell = '\n'.join(line[10:] for line in text[start:end].splitlines())
        for kind, explicit, pin, ok in [
            ('yueops', '', 'a' * 40, False),
            ('yueops', 'master', 'a' * 40, False),
            ('yueops', 'b' * 40, 'a' * 40, True),
            ('yueboard', '', 'a' * 40, True),
            ('yueboard', 'b' * 40, 'a' * 40, False),
        ]:
            with self.subTest(kind=kind, explicit=explicit):
                env = os.environ | {'target_plan': '{"validation_matrix":[{"validation":"' + kind + '"}]}',
                                    'explicit_board_ref': explicit, 'yueboard_contract_pin': pin}
                result = subprocess.run(['bash', '-c', 'set -euo pipefail\n' + shell],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok, result.stderr)
