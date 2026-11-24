
"""Generate an AgentRadar report using saved evidence and local Qwen."""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from gpt_researcher.actions.evidence_store import Evidence, EvidenceStore
from gpt_researcher.actions.decision_engine import DecisionEngine
from gpt_researcher.actions.local_report_writer import LocalReportWriter


def main():
    evidence_path = Path("output/agentradar/decision_evidence.json")

    if not evidence_path.exists():
        raise FileNotFoundError(
            "请先运行 python -m scripts.demo_decision"
        )

    # 1. 从磁盘恢复上一阶段保存的仓库证据
    data = json.loads(evidence_path.read_text(encoding="utf-8"))

    store = EvidenceStore()

    for item in data["evidence"]:
        evidence = Evidence(**item)
        store.records[evidence.evidence_id] = evidence

    # 2. 重新根据已保存的数据计算候选排序
    engine = DecisionEngine(required_language="Python")
    ranked = engine.rank(store)

    requirement = (
        "我想基于 Python 开发 Browser Agent，"
        "希望支持 MCP、能够本地部署、方便二次开发。"
        "请比较现有候选方案，推荐优先调研的项目。"
    )

    # 3. 调用本地 Qwen3:8b 解释评分结果
    writer = LocalReportWriter(model="qwen3:8b")
    result = writer.generate(requirement, ranked)

    # 4. 合并确定性评分与 AI 解读
    scoring_report = engine.render_markdown(ranked)
    ai_report = writer.render_analysis(requirement, result)

    output_dir = Path("output/agentradar")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "agentradar_final_draft.md"

    report_path.write_text(
        scoring_report + "\n---\n\n" + ai_report,
        encoding="utf-8",
    )

    print("Candidates:", len(ranked))
    print(
        "Selected:",
        result["selected"]["name"]
        if result["selected"] else "None",
    )
    print("Report:", report_path)


if __name__ == "__main__":
    main()