"""AgentRadar evidence integration smoke test."""

from gpt_researcher.actions.evidence_verifier import EvidenceVerifier
import asyncio
from dotenv import load_dotenv

load_dotenv()

from gpt_researcher import GPTResearcher


async def main():
    researcher = GPTResearcher(
        query="查询 GitHub 仓库的 Star 数量",
        verbose=False,
    )

    print(
        "Selected retrievers:",
        [cls.__name__ for cls in researcher.retrievers],
    )

    # Directly test the retrieval stage without calling an LLM.
    await researcher.research_conductor._search_relevant_source_urls(
        "browser agent"
    )

    store = researcher.evidence_store
    print("Evidence count:", len(store.records))

    if not store.records:
        raise RuntimeError("No evidence captured. Check routing and GitHub API.")

    first = next(iter(store.records.values()))
    # 选择一条确实包含 Language 字段的证据
    language_record = next(
        (
            record
            for record in store.records.values()
            if "Language:" in record.content
        ),
        None,
    )

    if language_record is None:
        raise RuntimeError("No evidence with a Language field was captured.")

    language_line = next(
        line for line in language_record.content.splitlines()
        if line.startswith("Language:")
    )
    language = language_line.split(":", 1)[1].strip()

    if not language or language == "Unknown":
        raise RuntimeError("The captured language value is unavailable.")

    claim = store.link_claim(
        f"项目主要使用 {language}",
        [language_record.evidence_id],
    )

    verifier = EvidenceVerifier(store)
    verification = verifier.verify_claim(claim)

    claim.status = verification["status"]
    claim.verification = verification
    print("Claim:", claim.text)
    print("Verification:", verification["status"])
    print("Reason:", verification["reason"])
    print("Evidence IDs:", verification["evidence_ids"])

    path = store.save_json(
        "output/agentradar/evidence_demo.json"
    )

    print("Saved to:", path)
    print("First evidence:", first.evidence_id)
    print("First source:", first.url)


if __name__ == "__main__":
    asyncio.run(main())