"""Live-mode pagination regressions, including the 2026-10-02 registry omission."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rescan_pagination", ROOT / "scripts/plan-rescan-targets.py")
assert SPEC is not None and SPEC.loader is not None
PLANNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLANNER)

# These three marker identities and times come from the actual registry pages
# read after build 36989604674. Unpromoted filler is minimized to the page floor.
PROMOTIONS = [
    (1326215557, "fb7d75561d64d06fd67d5ddb884c1714775ec6c9",
     "bc31e24be093407bb53b21c9d3f1735906f64031b81e434f0312c9ef6193fc9e", "2026-10-02T09:46:57Z"),
    (1323925675, "f9a1ca8751cbfde95f85de839fea9e9f535b50dd",
     "15b84efe5f5ee8d04d88f2f1a76f3071cd771768ef98c1bd385ecedc162d7ac2", "2026-10-01T20:43:27Z"),
    (1308203642, "6540fb1d99caba69e8c5a1d13c9ef55f2589273e",
     "e39c8426d60ff0878e9113229b15c7a2cd15f4a2bf4d852a2372b38381a78d85", "2026-09-29T01:31:51Z"),
]


def promotion(index: int) -> dict:
    identity, revision, digest, updated = PROMOTIONS[index]
    tags = [f"promoted-{revision}-{digest}"] + (["latest"] if index == 0 else [])
    return {"id": identity, "name": "sha256:" + digest, "updated_at": updated,
            "metadata": {"container": {"tags": tags}}}


def filler(start: int, count: int = 100) -> list[dict]:
    return [{"id": i, "name": f"sha256:{i:064x}", "updated_at": "2026-10-02T00:00:00Z",
             "metadata": {"container": {"tags": []}}} for i in range(start, start + count)]


def next_link(page: int, *, path: str = "/user/47652916/packages/container/yue-node/versions") -> str:
    return f'<https://api.github.com{path}?per_page=100&page={page}>; rel="next"'


class Response(io.BytesIO):
    def __init__(self, payload, link: str = "") -> None:
        super().__init__(json.dumps(payload).encode())
        self.headers = {"Link": link}


class RescanPaginationTest(unittest.TestCase):
    def fetch(self, replies: list, *, limit: int | None = None):
        calls = []

        def request(req, timeout):
            self.assertEqual(timeout, 30)
            self.assertEqual(req.get_header("Authorization"), "Bearer test-read-only")
            calls.append(req.full_url)
            reply = replies[len(calls) - 1]
            if isinstance(reply, Exception):
                raise reply
            payload, link = reply
            return Response(payload, link)

        with patch.dict(os.environ, {"GH_API_TOKEN": "test-read-only"}), \
             patch.object(PLANNER.urllib.request, "urlopen", side_effect=request):
            if limit is None:
                result = PLANNER.fetch_versions("yue-node")
            else:
                with patch.object(PLANNER, "MAX_VERSION_PAGES", limit):
                    result = PLANNER.fetch_versions("yue-node")
        return result, calls

    def test_real_page_two_promoted_digest_is_not_omitted(self) -> None:
        first = [promotion(0), promotion(1), *filler(1, 98)]
        versions, calls = self.fetch([(first, next_link(2)), ([promotion(2)], "")])
        matrix = PLANNER.plan([{"service": "yue-node", "platforms": "linux/amd64,linux/arm64"}],
                              lambda _: versions)["include"]
        self.assertEqual(len(matrix), 6)
        self.assertEqual({row["digest"] for row in matrix}, {"sha256:" + v[2] for v in PROMOTIONS})
        self.assertEqual({row["platform"] for row in matrix}, {"linux/amd64", "linux/arm64"})
        self.assertEqual([parse_qs(urlsplit(url).query)["page"] for url in calls], [["1"], ["2"]])

    def test_full_page_without_link_is_probed_to_a_terminal_page(self) -> None:
        versions, calls = self.fetch([(filler(1), ""), ([], "")])
        self.assertEqual(len(versions), 100)
        self.assertEqual(len(calls), 2)

    def test_short_page_with_next_link_is_not_truncated(self) -> None:
        versions, calls = self.fetch([([promotion(0)], next_link(2)), ([promotion(1)], "")])
        self.assertEqual(len(versions), 2)
        self.assertEqual(len(calls), 2)

    def test_fixed_owner_requests_accept_github_canonical_numeric_links(self) -> None:
        first_link = next_link(2) + ", " + next_link(2).replace('rel="next"', 'rel="last"')
        terminal_link = next_link(1).replace('rel="next"', 'rel="prev"') + ", " \
            + next_link(1).replace('rel="next"', 'rel="first"')
        _, calls = self.fetch([([promotion(0)], first_link), ([promotion(1)], terminal_link)])
        self.assertTrue(all(urlsplit(url).path == "/users/onesyue/packages/container/yue-node/versions"
                            for url in calls))
        self.assertTrue(all(urlsplit(url).netloc == "api.github.com" for url in calls))
        self.assertTrue(all(parse_qs(urlsplit(url).query)["per_page"] == ["100"] for url in calls))

    def test_terminal_page_below_bound_returns_complete_inventory(self) -> None:
        versions, _ = self.fetch([(filler(1), next_link(2)), ([promotion(0)], "")], limit=2)
        self.assertEqual(len(versions), 101)

    def test_full_page_at_bound_fails_closed_without_an_extra_request(self) -> None:
        with self.assertRaisesRegex(PLANNER.PlanError, "page limit"):
            self.fetch([(filler(1), next_link(2)), (filler(101), "")], limit=2)

    def test_continuation_at_bound_fails_closed_even_for_a_short_page(self) -> None:
        with self.assertRaisesRegex(PLANNER.PlanError, "page limit"):
            self.fetch([([promotion(0)], next_link(2)), ([promotion(1)], next_link(3))], limit=2)

    def test_incomplete_enumeration_never_publishes_a_partial_workflow_matrix(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "services.json").write_text(json.dumps([
                {"service": "yue-node", "platforms": "linux/amd64,linux/arm64"},
            ]), encoding="utf-8")
            output = root / "github-output"
            output.write_text("existing=value\n", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"GH_API_TOKEN": "test-read-only", "GITHUB_OUTPUT": str(output)}), \
                 patch.object(PLANNER, "ROOT", root), patch.object(PLANNER, "MAX_VERSION_PAGES", 1), \
                 patch.object(sys, "argv", ["plan-rescan-targets.py"]), \
                 patch.object(PLANNER.urllib.request, "urlopen", return_value=Response(
                     [promotion(0), promotion(1), *filler(1, 98)], next_link(2))), \
                 redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(PLANNER.main(), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing=value\n")
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("page limit", stderr.getvalue())

    def test_repeated_version_across_pages_fails_closed(self) -> None:
        with self.assertRaisesRegex(PLANNER.PlanError, "duplicate"):
            self.fetch([(filler(1), next_link(2)), ([filler(1, 1)[0]], "")])

    def test_duplicate_version_within_a_page_fails_closed(self) -> None:
        with self.assertRaisesRegex(PLANNER.PlanError, "duplicate"):
            self.fetch([([promotion(0), promotion(0)], "")])

    def test_changed_id_does_not_hide_a_repeated_digest(self) -> None:
        duplicate = copy.deepcopy(promotion(0))
        duplicate["id"] += 1
        with self.assertRaisesRegex(PLANNER.PlanError, "duplicate"):
            self.fetch([([promotion(0), duplicate], "")])

    def test_invalid_page_payloads_are_rejected(self) -> None:
        for payload in ({"message": "denied"}, ["not a version"], filler(1, 101),
                        [{**promotion(0), "id": True}], [{**promotion(0), "id": 0}],
                        [{**promotion(0), "name": None}]):
            with self.subTest(payload_type=type(payload).__name__, length=len(payload)), \
                 self.assertRaises(PLANNER.PlanError):
                self.fetch([(payload, "")])

    def test_empty_page_with_continuation_is_rejected(self) -> None:
        with self.assertRaisesRegex(PLANNER.PlanError, "empty"):
            self.fetch([([], next_link(2))])

    def test_untrusted_or_nonsequential_pagination_is_rejected(self) -> None:
        good = next_link(2)
        for link in (good.replace("https://api.github.com", "https://example.com"),
                     good.replace("https://", "http://"),
                     good.replace("/yue-node/", "/other-package/"),
                     good.replace("page=2", "page=1"), good.replace("page=2", "page=3"),
                     good.replace("per_page=100", "per_page=99"), good + ", " + good,
                     "malformed Link", good.replace('rel="next"', 'rel="unknown"'),
                     good.replace('rel="next"', 'rel="prev"'),
                     good.replace('rel="next"', 'rel="first"'),
                     good.replace('rel="next"', 'rel="last"'),
                     good + ", " + next_link(1).replace('rel="next"', 'rel="last"')):
            with self.subTest(link=link), self.assertRaisesRegex(PLANNER.PlanError, "pagination"):
                self.fetch([([promotion(0)], link)])

        with self.assertRaisesRegex(PLANNER.PlanError, "pagination"):
            self.fetch([([promotion(0)], good),
                        ([promotion(1)], next_link(1).replace('rel="next"', 'rel="last"'))])

    def test_second_page_network_failure_never_returns_first_page_only(self) -> None:
        with self.assertRaises(URLError):
            self.fetch([(filler(1), next_link(2)), URLError("unavailable")])


if __name__ == "__main__":
    unittest.main()
