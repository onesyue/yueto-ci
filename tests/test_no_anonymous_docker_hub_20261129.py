"""Validation never pulls anonymously from Docker Hub.

2026-11-29: yueops officials 46164820360 and 46172687868 failed on Docker Hub
toomanyrequests from shared runner IPs. Every fixed image reference in the
workflows and gate scripts names ghcr.io or mirror.gcr.io (same digests);
BuildKit base-image pulls go through the mirror first.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ("ghcr.io/", "mirror.gcr.io/", "${{")
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))


def fixed_images(text):
    found = re.findall(r"(?m)^[ \t]+image:[ \t]+([^\s#]+)", text)
    found += re.findall(r"driver-opts:[ \t]+image=([^\s#]+)", text)
    return found


class NoAnonymousDockerHub(unittest.TestCase):
    def test_workflow_images_name_ghcr_or_the_mirror(self):
        for workflow in WORKFLOWS:
            for image in fixed_images(workflow.read_text()):
                with self.subTest(workflow=workflow.name, image=image):
                    self.assertTrue(image.startswith(ALLOWED), image)

    def test_every_buildx_builder_mirrors_docker_hub(self):
        for workflow in WORKFLOWS:
            text = workflow.read_text()
            builders = text.count("uses: docker/setup-buildx-action@")
            mirrored = len(re.findall(
                r'buildkitd-config-inline: \|\n\s+\[registry\."docker\.io"\]\n\s+mirrors = \["mirror\.gcr\.io"\]\n',
                text))
            with self.subTest(workflow=workflow.name):
                self.assertEqual(builders, mirrored)

    def test_gate_scripts_pull_by_digest_from_the_mirror_first(self):
        ua = (ROOT / "scripts/validate-board-ua-cores.sh").read_text()
        self.assertRegex(ua, r"UA_GO_IMAGE='mirror\.gcr\.io/library/golang@sha256:[0-9a-f]{64}'")
        for name in ("ops-validation-lab-images.sh", "ops-validation-obligations.sh"):
            text = (ROOT / "scripts" / name).read_text()
            with self.subTest(script=name):
                self.assertLess(text.index("mirror.gcr.io/library/"), text.index("docker.io/library/"))

    def test_guard_rejects_a_bare_hub_image(self):
        self.assertFalse(all(i.startswith(ALLOWED) for i in fixed_images("        image: postgres:18@sha256:" + "0" * 64)))
        self.assertFalse(all(i.startswith(ALLOWED) for i in fixed_images("driver-opts: image=moby/buildkit:x@sha256:" + "0" * 64)))


if __name__ == "__main__":
    unittest.main()
