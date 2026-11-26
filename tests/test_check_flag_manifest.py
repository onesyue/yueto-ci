import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_flag_manifest import check


class FlagManifestTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.workflows = self.root / ".github/workflows"
        self.workflows.mkdir(parents=True)
        (self.root / "policy").mkdir()
        (self.root / "scripts").mkdir()
        self.workflow = self.workflows / "build.yml"
        self.workflow.write_text("""\
on:
  workflow_dispatch:
    inputs:
      validation_only:
        type: boolean
        default: false
jobs:
  build:
    env:
      CGO_ENABLED: '1'
      VALIDATION_ONLY: ${{ inputs.validation_only && 'true' || 'false' }}
      CAPACITY: ${{ vars.CAPACITY || '16' }}
      REUSE: ${{ vars.REUSE }}
    steps:
      - run: |
          echo "${VALIDATION_ONLY:-false}"
""")
        (self.workflows / "probe.yml").write_text('env:\n  CGO_ENABLED: "0" # probe\n')
        self.script = self.root / "scripts/board-validation.sh"
        self.script.write_text('test "${YUEBOARD_A11Y_SKIP:-0}" != 1\n')
        self.rows = [
            {"name": "CGO_ENABLED", "default": "1", "workflows": ["build.yml"]},
            {"name": "CGO_ENABLED", "default": "0", "workflows": ["probe.yml"]},
            {"name": "VALIDATION_ONLY", "default": "false", "input": "validation_only",
             "workflows": ["build.yml"]},
            {"name": "YUEBOARD_A11Y_SKIP", "default": "0", "scripts": ["board-validation.sh"]},
            {"name": "vars.CAPACITY", "kind": "value", "default": "16", "workflows": ["build.yml"]},
            {"name": "vars.REUSE", "default": "", "workflows": ["build.yml"]},
        ]
        self.write_manifest()

    def write_manifest(self):
        rows = [{"kind": "switch", **row} for row in self.rows]
        (self.root / "policy/flags.json").write_text(json.dumps({"flags": rows}))

    def mutate(self, path, before, after):
        original = path.read_text()
        self.assertIn(before, original)
        path.write_text(original.replace(before, after))

    def test_matches_reviewed_defaults_and_ignores_unrelated_text(self):
        with self.workflow.open("a") as out:
            out.write("          echo 'SKIP_EXAMPLE: yes'\n")
            out.write("      # env: ${{ vars.COMMENT }}\n")
            out.write("      - if: contains('vars.NOT_A_REFERENCE', 'vars.')\n")
            out.write("        run: echo done\n")
        self.assertEqual(check(self.root), [])

    def test_second_workflow_cannot_take_first_workflows_value(self):
        self.mutate(self.workflows / "probe.yml", '"0"', '"1"')
        self.assertEqual(check(self.root), [
            ".github/workflows/probe.yml: CGO_ENABLED differs from its reviewed default"])

    def test_changed_shell_default_requires_manifest_update(self):
        self.mutate(self.script, ":-0", ":-1")
        self.assertTrue(any("YUEBOARD_A11Y_SKIP" in error for error in check(self.root)))
        self.rows[3]["default"] = "1"
        self.write_manifest()
        self.assertEqual(check(self.root), [])

    def test_removed_shell_source_fails(self):
        self.script.unlink()
        self.assertIn("scripts/board-validation.sh: missing reviewed source for YUEBOARD_A11Y_SKIP",
                      check(self.root))

    def test_switch_like_env_literal_requires_review(self):
        for assignment in ["NEW_FLAG: YES", "FEATURE_MODE: observe"]:
            with self.subTest(assignment=assignment):
                (self.workflows / "new.yml").write_text("env:\n  " + assignment + "\n")
                self.assertTrue(any("has no manifest row" in error for error in check(self.root)))

    def test_unknown_vars_in_steps_conditions_and_sequences_fail(self):
        with self.workflow.open("a") as out:
            out.write("      - if: vars.NEW_CONDITION == 'yes'\n")
            out.write("        run: echo ${{ vars.NEW_SWITCH }}\n")
            out.write("        with:\n          values:\n            - ${{ vars.NEW_VALUE }}\n")
        errors = check(self.root)
        for name in ("NEW_CONDITION", "NEW_SWITCH", "NEW_VALUE"):
            self.assertIn(f".github/workflows/build.yml: vars.{name} has no manifest row", errors)

    def test_variable_fallback_drift(self):
        for original, changed in [("'16'", "'20'"), ("vars.REUSE", "vars.REUSE || '1'")]:
            with self.subTest(changed=changed):
                self.mutate(self.workflow, original, changed)
                self.assertTrue(any("reviewed default" in error for error in check(self.root)))
                self.mutate(self.workflow, changed, original)

    def test_validation_only_dispatch_binding_and_shell_default_agree(self):
        for before, after in [("default: false", "default: true"), ("default: false", "# removed"),
                              ("'true' || 'false'", "'true' || 'true'"), (":-false", ":-true")]:
            with self.subTest(after=after):
                self.mutate(self.workflow, before, after)
                self.assertTrue(check(self.root))
                self.mutate(self.workflow, after, before)


if __name__ == "__main__":
    unittest.main()
