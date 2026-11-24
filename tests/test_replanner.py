
import json
import tempfile
import unittest
from pathlib import Path

import requests

from gpt_researcher.actions.evidence_store import EvidenceStore
from gpt_researcher.actions.replanner import ResearchReplanner


class TestResearchReplanner(unittest.TestCase):

    def setUp(self):
        self.store = EvidenceStore()
        self.repo_url = "https://github.com/example/project"

    def make_claim(self, text="项目主要使用 Python", url=None, content=None):
        if url is None:
            url = self.repo_url
        if content is None:
            content = "Repository: example/project"

        eid = self.store.add_search_results(
            "GitHubSearch",
            "test query",
            [{
                "title": "example/project",
                "href": url,
                "raw_content": content,
            }],
        )[0]
        return self.store.link_claim(text, [eid])

    @staticmethod
    def fake_fetch(owner, repo):
        return {
            "title": f"{owner}/{repo}",
            "href": f"https://github.com/{owner}/{repo}",
            "raw_content": (
                f"Repository: {owner}/{repo}\n"
                "Language: Python\n"
                "Stars: 100"
            ),
        }

    def test_replan_success(self):
        claim = self.make_claim()

        replanner = ResearchReplanner(
            self.store, fetch_repo=self.fake_fetch
        )
        result = replanner.run(claim)

        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["replan_attempts"], 1)
        self.assertEqual(len(claim.evidence_ids), 2)
        self.assertEqual(claim.status, "supported")

    def test_no_retry_when_supported(self):
        claim = self.make_claim(
            content="Repository: example/project\nLanguage: Python"
        )

        def unexpected_fetch(owner, repo):
            raise AssertionError("Fetch should not be called")

        result = ResearchReplanner(
            self.store, fetch_repo=unexpected_fetch
        ).run(claim)

        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["replan_attempts"], 0)

    def test_unsupported_claim(self):
        claim = self.make_claim("项目适合企业生产环境")

        result = ResearchReplanner(
            self.store, fetch_repo=self.fake_fetch
        ).run(claim)

        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["replan_attempts"], 0)

    def test_api_failure(self):
        claim = self.make_claim()

        def failing_fetch(owner, repo):
            raise requests.Timeout("Connection timed out")

        result = ResearchReplanner(
            self.store, fetch_repo=failing_fetch
        ).run(claim)

        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["replan_attempts"], 1)

    def test_no_repository_url(self):
        claim = self.make_claim(url="https://example.org/article")

        result = ResearchReplanner(
            self.store, fetch_repo=self.fake_fetch
        ).run(claim)

        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["replan_attempts"], 0)

    def test_persistence_after_replan(self):
        claim = self.make_claim()

        result = ResearchReplanner(
            self.store, fetch_repo=self.fake_fetch
        ).run(claim)

        with tempfile.TemporaryDirectory() as directory:
            path = self.store.save_json(
                Path(directory) / "evidence.json"
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            saved_claim = payload["claims"][0]

            self.assertEqual(saved_claim["status"], "supported")
            self.assertEqual(
                saved_claim["verification"]["replan_attempts"], 1
            )


if __name__ == "__main__":
    unittest.main()