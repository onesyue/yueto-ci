"""The native runner must execute PATH-first doubles, not the next real binary."""
from __future__ import annotations

from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare-native-run-exec.sh"


class NativeRunExec(unittest.TestCase):
    def test_probe_accepts_an_executable_double_and_rejects_a_blind_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", str(SCRIPT), "--probe-only", directory],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_workflow_prepares_run_exec_before_native_nginx(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        backend = workflow.index("      - name: Validate yueops backend\n")
        prepare = workflow.index(
            'sudo -n env PATH="$PATH" bash .ci-policy/scripts/prepare-native-run-exec.sh',
            backend,
        )
        native = workflow.index(
            'sudo -n env PATH="$PATH" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" TZ=UTC '
            '"$PWD/.venv/bin/python" scripts/run-native-nginx-tests.py',
            backend,
        )
        self.assertLess(prepare, native)

    def test_script_refuses_to_remount_anything_except_run(self):
        source = SCRIPT.read_text()
        self.assertIn("[[ $target == /run ]] || fail", source)
        self.assertIn("mount -o remount,exec /run", source)
        self.assertNotIn("remount,exec /", source.replace("remount,exec /run", ""))
        mode = stat.S_IMODE(SCRIPT.stat().st_mode)
        self.assertTrue(mode & stat.S_IXUSR)
        self.assertIn("non-executable PATH-first", source)


if __name__ == "__main__":
    unittest.main()
