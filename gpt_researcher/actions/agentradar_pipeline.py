
"""AgentRadar unified GitHub research pipeline v0.1."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence_store import EvidenceStore
from .replanner import ResearchReplanner
from .decision_engine import DecisionEngine
from .local_report_writer import LocalReportWriter
from gpt_researcher.retrievers.github.github_search import GitHubSearch


class AgentRadarPipeline:
    def __init__(self, search_fn=None, writer=None, now=None):
        self.search_fn = search_fn or (
            lambda query, limit: GitHubSearch(query).search(limit)
        )
        self.writer = writer or LocalReportWriter(
            model="qwen3:8b"
        )
        self.now = now or datetime.now(timezone.utc)

    def run(
        self,
        requirement: str,
        github_query: str,
        output_dir="output/agentradar",
        max_results=8,
    ):
        # 1. Research: fetch GitHub repository data.
        results = self.search_fn(github_query, max_results)

        if not results:
            raise RuntimeError("GitHub search returned no results.")

        # 2. Store evidence.
        store = EvidenceStore()
        ids = store.add_search_results(
            source="GitHubSearch",
            query=github_query,
            results=results,
        )

        if not ids:
            raise RuntimeError("No valid evidence was captured.")

        # 3. Verify the Python-language requirement.
        verification_results = []

        for evidence_id in dict.fromkeys(ids):
            claim = store.link_claim(
                "项目主要使用 Python",
                [evidence_id],
            )

            replanner = ResearchReplanner(
                store,
                max_retries=1,
            )
            result = replanner.run(claim)

            verification_results.append({
                "evidence_id": evidence_id,
                "status": result["status"],
                "reason": result["reason"],
                "attempts": result["replan_attempts"],
            })

        # 4. Compute explainable metadata scores.
        engine = DecisionEngine(
            required_language="Python",
            now=self.now,
        )
        ranked = engine.rank(store)

        # 5. Generate local Qwen analysis.
        llm_result = self.writer.generate(
            requirement,
            ranked,
        )

        metadata_report = engine.render_markdown(ranked)
        ai_report = self.writer.render_analysis(
            requirement,
            llm_result,
        )

        # Scores can tie. Alphabetical sorting is not
        # evidence that one project is technically better.
        eligible = [
            item for item in ranked
            if item["status"] == "eligible"
            and item["score"] is not None
        ]

        tie_notice = ""
        if (
            len(eligible) >= 2
            and eligible[0]["score"] == eligible[1]["score"]
        ):
            tie_notice = (
                "\n\n> 注意：最高分存在并列。"
                "当前稳定排序不能证明第一个项目技术能力更强。"
            )

        verification_lines = [
            "## 规则核验记录",
            "",
        ]

        for item in verification_results:
            verification_lines.append(
                f"- `{item['evidence_id']}`: "
                f"{item['status']} — {item['reason']}"
            )

        report = "\n".join([
            metadata_report,
            "---",
            ai_report,
            tie_notice,
            "\n".join(verification_lines),
            "",
            "## 结论边界",
            "",
            "本报告仅完成 GitHub 元数据筛选和部分规则核验。",
            "MCP、本地部署、代码架构、Benchmark 等"
            "尚未完成独立证据验证。",
            "模型生成的自然语言解释也尚未逐句核验。",
        ])

        # 6. Save all outputs.
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        evidence_path = store.save_json(
            output / "evidence.json"
        )

        report_path = output / "report.md"
        report_path.write_text(
            report,
            encoding="utf-8",
        )

        summary = {
            "requirement": requirement,
            "github_query": github_query,
            "candidate_count": len(ranked),
            "eligible_count": len(eligible),
            "selected": (
                llm_result["selected"]["name"]
                if llm_result["selected"] else None
            ),
            "verification": verification_results,
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
            "candidates": ranked,
        }

        summary_path = output / "run_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return summary