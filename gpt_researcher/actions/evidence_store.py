
"""AgentRadar Evidence Store v0.1."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit


@dataclass
class Evidence:
    evidence_id: str
    source: str
    url: str
    title: str
    content: str
    content_kind: str
    content_sha256: str
    retrieved_at: str
    queries: list[str]


@dataclass
class Claim:
    text: str
    evidence_ids: list[str]
    status: str = "unverified"
    verification: dict | None = None


class EvidenceStore:
    def __init__(self):
        self.records: dict[str, Evidence] = {}
        self.claims: list[Claim] = []

    def add_search_results(
        self, source: str, query: str, results: list[dict]
    ) -> list[str]:
        """Record search results without treating them as verified facts."""
        added_ids = []

        for item in results:
            if not isinstance(item, dict):
                continue

            url = item.get("href") or item.get("url")
            if not isinstance(url, str):
                continue

            try:
                parts = urlsplit(url)
            except ValueError:
                continue

            if parts.scheme not in {"https", "http"} or not parts.netloc or parts.username:
                continue

            raw = item.get("raw_content")
            if isinstance(raw, str) and raw.strip():
                content, kind = raw.strip(), "raw_content"
            else:
                body = item.get("body")
                if not isinstance(body, str) or not body.strip():
                    continue
                content, kind = body.strip(), "search_snippet"

            content_hash = sha256(content.encode("utf-8")).hexdigest()
            evidence_id = sha256(
                f"{source}\n{url}\n{content_hash}".encode("utf-8")
            ).hexdigest()[:16]

            if evidence_id not in self.records:
                title = item.get("title")
                self.records[evidence_id] = Evidence(
                    evidence_id=evidence_id,
                    source=source,
                    url=url,
                    title=title if isinstance(title, str) and title.strip() else url,
                    content=content,
                    content_kind=kind,
                    content_sha256=content_hash,
                    retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    queries=[query],
                )
            elif query not in self.records[evidence_id].queries:
                self.records[evidence_id].queries.append(query)

            added_ids.append(evidence_id)

        return added_ids

    def link_claim(self, text: str, evidence_ids: list[str]) -> Claim:
        """Associate sources with a claim; verification is still pending."""
        unique_ids = list(dict.fromkeys(evidence_ids))

        if not text.strip() or not unique_ids:
            raise ValueError("Claim text and evidence IDs are required")

        missing = [eid for eid in unique_ids if eid not in self.records]
        if missing:
            raise ValueError(f"Unknown evidence IDs: {missing}")

        claim = Claim(text=text.strip(), evidence_ids=unique_ids)
        self.claims.append(claim)
        return claim

    def save_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_version": "0.1",
            "evidence": [asdict(record) for record in self.records.values()],
            "claims": [asdict(claim) for claim in self.claims],
        }

        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target