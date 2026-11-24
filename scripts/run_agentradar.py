
"""Command-line entry point for AgentRadar."""

import argparse

from dotenv import load_dotenv

# Load local Ollama configuration before the pipeline runs.
load_dotenv()

from gpt_researcher.actions.agentradar_pipeline import AgentRadarPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run AgentRadar GitHub research pipeline"
    )

    parser.add_argument(
        "--requirement",
        default=(
            "我想使用 Python 开发 Browser Agent，"
            "希望支持 MCP、本地部署和二次开发。"
        ),
    )

    parser.add_argument(
        "--query",
        default="browser agent language:Python archived:false",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    pipeline = AgentRadarPipeline()

    summary = pipeline.run(
        requirement=args.requirement,
        github_query=args.query,
        max_results=args.max_results,
    )

    print("\n=== AgentRadar Run Summary ===")
    print("Candidates:", summary["candidate_count"])
    print("Eligible:", summary["eligible_count"])
    print("Selected:", summary["selected"])
    print("Report:", summary["report_path"])
    print("Evidence:", summary["evidence_path"])


if __name__ == "__main__":
    main()