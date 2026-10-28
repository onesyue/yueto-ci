"""Keep the central PostgreSQL service on its reviewed immutable image."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"


class PostgresImagePinTest(unittest.TestCase):
    def assert_pin(self, workflow):
        # Anchor to the service consumer, not an unrelated comment or command.
        images = re.findall(
            r"^    services:\n      postgres:\n        image: ([^\n]+)$",
            workflow, re.M,
        )
        self.assertEqual(images, [IMAGE])

    def test_reviewed_service_pin(self):
        self.assert_pin((ROOT / ".github/workflows/build.yml").read_text())

    def test_drift_missing_and_commented_service_are_rejected(self):
        source = (ROOT / ".github/workflows/build.yml").read_text()
        for replacement in ("postgres:18", "postgres:17-alpine", "postgres:18.6-alpine",
                            IMAGE[:-1] + "1", ""):
            with self.subTest(replacement=replacement), self.assertRaises(AssertionError):
                self.assert_pin(source.replace(IMAGE, replacement))
        for broken in (source.replace("      postgres:", "      removed:"),
                       source.replace("        image: " + IMAGE, "        # image: " + IMAGE)):
            with self.assertRaises(AssertionError):
                self.assert_pin(broken)


if __name__ == "__main__":
    unittest.main()
