
"""AgentRadar bounded evidence replanning v0.1."""

import os
from urllib.parse import urlsplit

import requests

from .evidence_verifier import EvidenceVerifier


class ResearchReplanner:
    def __init__(self, store, max_retries=1, fetch_repo=None):
        self.store = store
        self.verifier = EvidenceVerifier(store)
        self.max_retries = max(0, min(int(max_retries), 2))
        self.fetch_repo = fetch_repo or self._fetch_repo

    @staticmethod
    def _repo_from_url(url):
        """Only allow canonical GitHub repository URLs."""
        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")

        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "github.com"
            or parsed.username is not None
            or len(parts) != 2
        ):
            return None

        owner, repo = parts
        allowed = set(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        )

        if not owner or not repo:
            return None
        if any(ch not in allowed for ch in owner + repo):
            return None

        return owner, repo

    @staticmethod
    def _needs_metadata(result):
        """Retry only for supported metadata gaps."""
        if result["status"] != "insufficient":
            return False

        reason = result.get("reason", "")
        return any(
            field in reason
            for field in (
                "Language field",
                "Stars value",
                "Last pushed date",
            )
        )

    @staticmethod
    def _fetch_repo(owner, repo):
        """Fetch additional details from GitHub REST API."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }

        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Invalid GitHub repository response")

        full_name = data.get("full_name")
        url = data.get("html_url")

        if (
            not isinstance(full_name, str)
            or full_name.casefold() != f"{owner}/{repo}".casefold()
            or url != f"https://github.com/{full_name}"
        ):
            raise ValueError("Repository identity mismatch")

        lines = [
            f"Repository: {full_name}",
            f"URL: {url}",
        ]

        language = data.get("language")
        stars = data.get("stargazers_count")
        pushed = data.get("pushed_at")

        if isinstance(language, str) and language:
            lines.append(f"Language: {language}")
        if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0:
            lines.append(f"Stars: {stars}")
        if isinstance(pushed, str) and pushed:
            lines.append(f"Last pushed: {pushed}")

        return {
            "title": full_name,
            "href": url,
            "body": data.get("description") or "",
            "raw_content": "\n".join(lines),
        }

    def run(self, claim):
        """Verify -> fetch missing metadata -> verify again."""
        result = self.verifier.verify_claim(claim)
        attempts = 0
        note = "No supplementary search was necessary."

        if self._needs_metadata(result):
            repo_info = None

            for evidence_id in claim.evidence_ids:
                record = self.store.records.get(evidence_id)
                if record is not None:
                    repo_info = self._repo_from_url(record.url)
                    if repo_info:
                        break

            if repo_info is None:
                note = "No usable GitHub repository URL."
            else:
                owner, repo = repo_info

                for _ in range(self.max_retries):
                    attempts += 1

                    try:
                        item = self.fetch_repo(owner, repo)
                        new_ids = self.store.add_search_results(
                            source="GitHubRepoDetails",
                            query=f"repository metadata {owner}/{repo}",
                            results=[item],
                        )
                    except (requests.RequestException, ValueError, TypeError) as exc:
                        note = f"Supplementary lookup failed: {type(exc).__name__}"
                        break

                    fresh_ids = [
                        eid for eid in new_ids
                        if eid not in claim.evidence_ids
                    ]

                    if not fresh_ids:
                        note = "No new evidence returned."
                        break

                    claim.evidence_ids.extend(fresh_ids)
                    result = self.verifier.verify_claim(claim)

                    if result["status"] != "insufficient":
                        note = "Claim rechecked after supplementary retrieval."
                        break

                    note = "Claim is still insufficient after retrieval."

        # Update the existing Claim object and its serialized state.
        claim.status = result["status"]
        claim.verification = {
            **result,
            "replan_attempts": attempts,
            "replan_note": note,
        }

        return claim.verification