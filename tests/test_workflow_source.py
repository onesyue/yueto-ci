"""Workflow assertions must fail when source files cannot be read."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workflow_source


class WorkflowSourceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        root_patch = patch.object(workflow_source, "ROOT", root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.workflow = root / ".github/workflows/build.yml"
        self.shared_script = root / "scripts/ops-validation-fixture.sh"

    def write_workflow(self):
        self.workflow.parent.mkdir(parents=True)
        self.workflow.write_text(
            '        run: |\n'
            '          bash "$GITHUB_WORKSPACE/.ci-policy/scripts/ops-validation-fixture.sh"\n',
            encoding="utf-8",
        )

    def test_missing_workflow_fails_at_the_source_path(self):
        with self.assertRaises(FileNotFoundError) as failure:
            workflow_source.workflow_text()
        self.assertEqual(failure.exception.filename, str(self.workflow))

    def test_missing_shared_script_fails_at_the_reference_path(self):
        self.write_workflow()
        with self.assertRaises(FileNotFoundError) as failure:
            workflow_source.workflow_text()
        self.assertEqual(failure.exception.filename, str(self.shared_script))

    def test_existing_shared_script_is_expanded(self):
        self.write_workflow()
        self.shared_script.parent.mkdir()
        self.shared_script.write_text(
            "#!/bin/bash\n# Shared by build.yml\necho fixture\n",
            encoding="utf-8",
        )
        self.assertEqual(workflow_source.workflow_text(), "        run: |\n          echo fixture\n")
