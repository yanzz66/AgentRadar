
"""AgentRadar real GitHub replanning demo."""

from dotenv import load_dotenv

load_dotenv()

from gpt_researcher.actions.evidence_store import EvidenceStore
from gpt_researcher.actions.replanner import ResearchReplanner


def main():
    store = EvidenceStore()

    # Intentionally incomplete evidence for testing the retry path.
    original = [{
        "title": "browser-use/browser-use",
        "href": "https://github.com/browser-use/browser-use",
        "raw_content": (
            "Repository: browser-use/browser-use\n"
            "URL: https://github.com/browser-use/browser-use"
        ),
    }]

    ids = store.add_search_results(
        "GitHubSearch", "browser agent", original
    )
    claim = store.link_claim("项目主要使用 Python", ids)

    replanner = ResearchReplanner(store, max_retries=1)

    print("Before:", replanner.verifier.verify_claim(claim)["status"])

    result = replanner.run(claim)

    print("After:", result["status"])
    print("Reason:", result["reason"])
    print("Replan attempts:", result["replan_attempts"])
    print("Note:", result["replan_note"])
    print("Evidence count:", len(store.records))

    path = store.save_json(
        "output/agentradar/replan_demo.json"
    )
    print("Saved to:", path)


if __name__ == "__main__":
    main()