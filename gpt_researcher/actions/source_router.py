
"""AgentRadar Source Router v0.1 - task-level rule routing."""

import re


REPO_EN = (
    "github", "repo", "repos", "repository", "repositories",
    "star", "stars", "fork", "forks", "commit", "commits",
    "issue", "issues", "pull request", "pull requests",
    "open source", "open-source",
)

WEB_EN = (
    "compare", "comparison", "benchmark", "benchmarks",
    "docs", "documentation", "paper", "papers",
    "tutorial", "architecture",
)

REPO_CN = ("仓库", "开源", "星标", "提交记录", "维护活跃度")
WEB_CN = ("文档", "论文", "对比", "比较", "选型", "评测", "架构", "原理", "教程", "性能", "官方")


def _has_english_keyword(text: str, keywords: tuple) -> bool:
    return any(
        re.search(rf"\b{re.escape(word)}\b", text)
        for word in keywords
    )


def select_sources(query: str) -> tuple[str, ...]:
    """Return data sources based on the research task."""
    text = query.casefold() if isinstance(query, str) else ""

    need_github = (
        _has_english_keyword(text, REPO_EN)
        or any(word in text for word in REPO_CN)
    )
    need_web = (
        _has_english_keyword(text, WEB_EN)
        or any(word in text for word in WEB_CN)
    )

    if need_github and need_web:
        # Tavily first: the original planner uses the first retriever.
        return ("tavily", "github")

    if need_github:
        return ("github",)

    return ("tavily",)


def route_retrievers(query: str, retrievers: list) -> list:
    """Select registered retriever classes for one research task."""
    original = list(retrievers)
    by_name = {cls.__name__.lower(): cls for cls in original}

    # v0.1 only changes the known Tavily + GitHub configuration.
    # Other configurations remain untouched.
    if len(original) != 2 or set(by_name) != {
        "tavilysearch", "githubsearch"
    }:
        return original

    class_names = {
        "tavily": "tavilysearch",
        "github": "githubsearch",
    }

    return [
        by_name[class_names[source]]
        for source in select_sources(query)
    ]