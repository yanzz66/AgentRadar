"""GitHub repository search retriever for AgentRadar v0.1."""

import os
from datetime import datetime,timezone

import requests

class GitHubSearch:
    """Search public GitHub repositories and normalize their metadata."""
    requires_scraping = False
    API_URL = "https://api.github.com/search/repositories"
    def __init__(self, query: str, headers=None, query_domains=None):
        self.query = query.strip() if isinstance(query, str) else ""
        self.token = (headers or {}).get("github_token") or os.getenv("GITHUB_TOKEN")
        self.query_domains = query_domains or []
    def search(self, max_results=10):
        limit = max(0, min(int(max_results),100))
        if not self.query or limit == 0:
            return []
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = requests.get(
            self.API_URL,
            params={"q": self.query, "per_page": limit},
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Unexpected GitHub search response format")

        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        results = []
        seen = set()

        for repo in payload["items"]:
            if not isinstance(repo, dict):
                continue

            name, url = repo.get("full_name"), repo.get("html_url")
            if not isinstance(name, str) or not name:
                continue
            if not isinstance(url, str) or not url.startswith("https://github.com/"):
                continue
            if url in seen:
                continue
            seen.add(url)

            description = " ".join(str(repo.get("description") or "").split())[:500]
            license_info = repo.get("license")
            license_name = (
                    license_info.get("spdx_id") or "Unknown"
            ) if isinstance(license_info, dict) else "Unknown"

            topics = repo.get("topics")
            topic_names = ", ".join(str(t) for t in topics[:10]) if isinstance(topics, list) else ""

            raw_content = "\n".join([
                f"Repository: {name}",
                f"URL: {url}",
                f"Description: {description}",
                f"Language: {repo.get('language') or 'Unknown'}",
                f"Stars: {repo.get('stargazers_count', 'Unknown')}",
                f"Forks: {repo.get('forks_count', 'Unknown')}",
                f"Archived: {repo.get('archived', 'Unknown')}",
                f"License: {license_name}",
                f"Topics: {topic_names}",
                f"Last pushed: {repo.get('pushed_at') or 'Unknown'}",
                f"Retrieved at (UTC): {fetched_at}",
            ])

            results.append({
                "title": name,
                "href": url,
                "body": description,
                "raw_content": raw_content,
            })

        return results