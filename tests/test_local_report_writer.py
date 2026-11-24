
import json
import unittest
from unittest.mock import patch, Mock

from gpt_researcher.actions.local_report_writer import LocalReportWriter


CANDIDATE = {
    "name": "example/browser-agent",
    "url": "https://github.com/example/browser-agent",
    "evidence_id": "abc123",
    "status": "eligible",
    "score": 85,
    "stars": 4000,
    "license": "MIT",
    "days_since_push": 10,
    "reasons": ["Recent activity", "Community interest"],
}


class TestLocalReportWriter(unittest.TestCase):

    @patch("gpt_researcher.actions.local_report_writer.requests.post")
    def test_valid_model_output(self, mock_post):
        output = {
            "summary": "该项目值得进一步调研。",
            "risks": ["尚未验证真实任务性能"],
            "questions_to_verify": ["是否支持 MCP？"],
        }

        mock_post.return_value = Mock(
            json=lambda: {
                "message": {
                    "content": json.dumps(output, ensure_ascii=False)
                }
            }
        )

        writer = LocalReportWriter()
        result = writer.generate("开发 Browser Agent", [CANDIDATE])

        self.assertEqual(
            result["selected"]["name"], "example/browser-agent"
        )
        self.assertEqual(result["analysis"]["summary"], output["summary"])

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertFalse(payload["stream"])

    @patch("gpt_researcher.actions.local_report_writer.requests.post")
    def test_no_eligible_candidate(self, mock_post):
        writer = LocalReportWriter()
        excluded = {**CANDIDATE, "status": "excluded", "score": None}

        result = writer.generate("开发 Browser Agent", [excluded])

        self.assertIsNone(result["selected"])
        mock_post.assert_not_called()

    @patch("gpt_researcher.actions.local_report_writer.requests.post")
    def test_invalid_output_rejected(self, mock_post):
        mock_post.return_value = Mock(
            json=lambda: {
                "message": {
                    "content": json.dumps({
                        "summary": "分析",
                        "risks": "not a list",
                        "questions_to_verify": [],
                    })
                }
            }
        )

        with self.assertRaises(ValueError):
            LocalReportWriter().generate(
                "开发 Browser Agent", [CANDIDATE]
            )


if __name__ == "__main__":
    unittest.main()