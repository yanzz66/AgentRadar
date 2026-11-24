import unittest
from unittest.mock import patch, Mock

from gpt_researcher.retrievers.github.github_search import GitHubSearch

class TestGitHubSearch(unittest.TestCase):
    @patch("gpt_researcher.retrievers.github.github_search.requests.get")
    def test_normal_result(self, mock_get):
        repo = {
            "full_name": "example/browser-agent",
            "html_url": "https://github.com/example/browser-agent",
            "description": "A browser agent",
            "stargazers_count": 100,
        }
        mock_get.return_value = Mock(
            json=lambda: {"items": [repo, repo]}
        )

        results = GitHubSearch("browser agent").search(3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "example/browser-agent")
        self.assertIn("Stars: 100", results[0]["raw_content"])

    @patch("gpt_researcher.retrievers.github.github_search.requests.get")
    def test_empty_query(self, mock_get):
        results = GitHubSearch("").search()

        self.assertEqual(results, [])
        mock_get.assert_not_called()

    @patch("gpt_researcher.retrievers.github.github_search.requests.get")
    def test_invalid_response(self, mock_get):
        mock_get.return_value = Mock(
            json=lambda: {"unexpected": True}
        )

        with self.assertRaises(ValueError):
            GitHubSearch("browser agent").search()


if __name__ == "__main__":
    unittest.main()