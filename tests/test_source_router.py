
import unittest

from gpt_researcher.actions.source_router import (
    select_sources,
    route_retrievers,
)


class TavilySearch:
    pass


class GitHubSearch:
    pass


class OtherRetriever:
    pass


class TestSourceRouter(unittest.TestCase):

    def setUp(self):
        self.available = [TavilySearch, GitHubSearch]

    def test_github_query(self):
        selected = route_retrievers(
            "查询 GitHub 仓库的 stars 和 commits",
            self.available,
        )
        self.assertEqual(selected, [GitHubSearch])

    def test_web_query(self):
        selected = route_retrievers(
            "解释 RAG 的基本原理",
            self.available,
        )
        self.assertEqual(selected, [TavilySearch])

    def test_mixed_query(self):
        selected = route_retrievers(
            "对比 GitHub 开源 Agent 项目的架构",
            self.available,
        )
        self.assertEqual(selected, [TavilySearch, GitHubSearch])

    def test_empty_query(self):
        self.assertEqual(select_sources(""), ("tavily",))

    def test_missing_provider(self):
        selected = route_retrievers(
            "查询 GitHub 仓库",
            [TavilySearch],
        )
        self.assertEqual(selected, [TavilySearch])

    def test_other_provider_unchanged(self):
        original = [TavilySearch, GitHubSearch, OtherRetriever]
        selected = route_retrievers(
            "查询 GitHub 仓库",
            original,
        )
        self.assertEqual(selected, original)


if __name__ == "__main__":
    unittest.main()