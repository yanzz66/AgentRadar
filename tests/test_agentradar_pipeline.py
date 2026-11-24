
import json
import tempfile
import unittest
from datetime import datetime, timezone

from gpt_researcher.actions.agentradar_pipeline import AgentRadarPipeline
from gpt_researcher.actions.local_report_writer import LocalReportWriter


NOW = datetime.now(timezone.utc)


def fake_search(query, limit):
    return [{
        "title": "example/browser-agent",
        "href": "https://github.com/example/browser-agent",
        "raw_content": "\n".join([
            "Repository: example/browser-agent",
            "Language: Python",
            "Stars: 12000",
            "Archived: False",
            "License: MIT",
            f"Last pushed: {NOW.isoformat()}",
        ]),
    }]


class FakeWriter:
    def generate(self, requirement, ranked):
        eligible = [
            item for item in ranked
            if item["status"] == "eligible"
        ]
        selected = eligible[0] if eligible else None

        return {
            "selected": selected,
            "analysis": {
                "summary": "候选项目值得进一步研究。",
                "risks": ["MCP 支持情况尚未核验"],
                "questions_to_verify": ["是否支持本地部署？"],
            } if selected else None,
        }

    render_analysis = staticmethod(
        LocalReportWriter.render_analysis
    )


class TestAgentRadarPipeline(unittest.TestCase):

    def test_end_to_end_without_network(self):
        pipeline = AgentRadarPipeline(
            search_fn=fake_search,
            writer=FakeWriter(),
            now=NOW,
        )

        with tempfile.TemporaryDirectory() as directory:
            summary = pipeline.run(
                requirement="开发 Python Browser Agent",
                github_query="browser agent",
                output_dir=directory,
            )

            self.assertEqual(summary["candidate_count"], 1)
            self.assertEqual(summary["eligible_count"], 1)
            self.assertEqual(
                summary["selected"],
                "example/browser-agent",
            )

            self.assertEqual(
                summary["verification"][0]["status"],
                "supported",
            )

            from pathlib import Path

            output = Path(directory)
            self.assertTrue((output / "report.md").exists())
            self.assertTrue((output / "evidence.json").exists())
            self.assertTrue(
                (output / "run_summary.json").exists()
            )

            evidence = json.loads(
                (output / "evidence.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                evidence["claims"][0]["status"],
                "supported",
            )
            self.assertIsNotNone(
                evidence["claims"][0]["verification"]
            )

            report = (output / "report.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("example/browser-agent", report)
            self.assertIn("Evidence ID", report)

    def test_empty_search_fails_clearly(self):
        pipeline = AgentRadarPipeline(
            search_fn=lambda query, limit: [],
            writer=FakeWriter(),
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                pipeline.run(
                    "开发 Browser Agent",
                    "browser agent",
                    output_dir=directory,
                )


if __name__ == "__main__":
    unittest.main()