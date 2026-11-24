
"""AgentRadar GitHub metadata decision demo."""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from gpt_researcher.retrievers.github.github_search import GitHubSearch
from gpt_researcher.actions.evidence_store import EvidenceStore
from gpt_researcher.actions.decision_engine import DecisionEngine


def main():
    query = "browser agent language:Python archived:false"

    # 1. 获取本轮真实 GitHub 搜索结果
    results = GitHubSearch(query).search(8)

    if not results:
        raise RuntimeError("GitHub search returned no repositories.")

    # 2. 记录本轮证据
    store = EvidenceStore()
    store.add_search_results(
        source="GitHubSearch",
        query=query,
        results=results,
    )

    # 3. 执行规则筛选和评分
    engine = DecisionEngine(required_language="Python")
    ranked = engine.rank(store)

    # 4. 生成可解释报告
    report = engine.render_markdown(ranked)

    output_dir = Path("output/agentradar")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "decision_report.md"
    report_path.write_text(report, encoding="utf-8")

    evidence_path = store.save_json(
        output_dir / "decision_evidence.json"
    )

    for item in ranked:
        print(
            item["name"],
            "status:", item["status"],
            "score:", item["score"],
        )

    print("Report:", report_path)
    print("Evidence:", evidence_path)


if __name__ == "__main__":
    main()