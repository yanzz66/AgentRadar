
"""AgentRadar: explainable GitHub metadata screening."""

from datetime import datetime, timezone
from urllib.parse import urlsplit


class DecisionEngine:
    def __init__(self, required_language="Python", now=None):
        self.required_language = required_language.casefold()
        self.now = now or datetime.now(timezone.utc)

    @staticmethod
    def _fields(content):
        """Convert normalized evidence lines into a dictionary."""
        fields = {}
        for line in content.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip().casefold()] = value.strip()
        return fields

    def evaluate(self, evidence):
        """Evaluate one GitHub repository evidence record."""
        if (
            evidence.source != "GitHubSearch"
            or evidence.content_kind != "raw_content"
        ):
            raise ValueError("Expected raw GitHubSearch evidence")

        fields = self._fields(evidence.content)
        url = evidence.url
        parts = urlsplit(url)

        if (
            parts.scheme != "https"
            or parts.netloc.lower() != "github.com"
            or len(parts.path.strip("/").split("/")) != 2
        ):
            raise ValueError("Not a GitHub repository URL")

        name = fields.get("repository") or evidence.title
        reasons = []
        status = "eligible"

        lang = fields.get("language", "Unknown")
        archived = fields.get("archived", "Unknown").casefold()
        license_name = fields.get("license", "Unknown")

        stars_raw = fields.get("stars", "")
        try:
            stars = int(stars_raw.replace(",", ""))
            if stars < 0:
                raise ValueError()
        except (ValueError, AttributeError):
            stars = None

        pushed = fields.get("last pushed", "")
        days = None

        try:
            date = datetime.fromisoformat(
                pushed.replace("Z", "+00:00")
            )
            if date.tzinfo is None:
                raise ValueError()
            days = (
                self.now - date.astimezone(timezone.utc)
            ).total_seconds() / 86400

            if days < 0:
                days = None
        except ValueError:
            pass

        # Step 1: Hard constraints.
        if archived == "true":
            status = "excluded"
            reasons.append("Repository is archived")

        if lang.casefold() not in (
            self.required_language, "unknown"
        ):
            status = "excluded"
            reasons.append(
                f"Language {lang} does not meet {self.required_language}"
            )

        # Step 2: Check whether metadata is sufficient.
        if status != "excluded":
            gaps = []

            if lang.casefold() == "unknown":
                gaps.append("language")
            if archived not in ("true", "false"):
                gaps.append("archived")
            if stars is None:
                gaps.append("stars")
            if days is None:
                gaps.append("last pushed")
            if license_name.casefold() in (
                "unknown", "noassertion", "none", ""
            ):
                gaps.append("license")

            if gaps:
                status = "needs_review"
                reasons.append(
                    "Missing/uncertain metadata: " + ", ".join(gaps)
                )

        # Step 3: Score only eligible repositories.
        score = None

        if status == "eligible":
            activity = (
                50 if days <= 30 else
                35 if days <= 90 else
                20 if days <= 180 else
                5 if days <= 365 else 0
            )

            community = (
                30 if stars >= 10000 else
                24 if stars >= 3000 else
                15 if stars >= 500 else
                8 if stars >= 100 else 2
            )

            score = activity + community + 20

            reasons.append(
                f"Activity {activity}/50 "
                f"(last push {days:.0f} days ago)"
            )
            reasons.append(
                f"Community {community}/30 ({stars} stars)"
            )
            reasons.append(
                "License metadata present 20/20 "
                "(compatibility not assessed)"
            )

        return {
            "name": name,
            "url": url,
            "evidence_id": evidence.evidence_id,
            "status": status,
            "score": score,
            "stars": stars,
            "language": lang,
            "license": license_name,
            "days_since_push": (
                None if days is None else round(days, 1)
            ),
            "reasons": reasons,
        }

    def rank(self, store):
        """Rank repositories from a fresh EvidenceStore."""
        candidates = []
        seen = set()

        for evidence in store.records.values():
            if (
                evidence.source != "GitHubSearch"
                or evidence.content_kind != "raw_content"
            ):
                continue

            if evidence.url in seen:
                continue

            seen.add(evidence.url)
            candidates.append(self.evaluate(evidence))

        return sorted(
            candidates,
            key=lambda item: (
                {
                    "eligible": 0,
                    "needs_review": 1,
                    "excluded": 2,
                }[item["status"]],
                -(
                    item["score"]
                    if item["score"] is not None else -1
                ),
                item["name"].lower(),
            ),
        )

    @staticmethod
    def render_markdown(candidates):
        """Create an explainable metadata-screening report."""
        lines = [
            "# AgentRadar — GitHub metadata shortlist",
            "",
            "*Metadata-only screening, not a final technical recommendation.*",
            "",
            "Scoring: push recency 50 + stars 30 + license metadata 20.",
            "MCP, local deployment and architecture require separate verification.",
            "",
            "| Repository | Status | Score | Stars | License | Evidence |",
            "|---|---|---:|---:|---|---|",
        ]

        for item in candidates:
            cells = [
                f"[{item['name']}]({item['url']})",
                item["status"],
                str(item["score"]) if item["score"] is not None else "—",
                str(item["stars"]) if item["stars"] is not None else "—",
                item["license"],
                f"`{item['evidence_id']}`",
            ]
            lines.append("| " + " | ".join(cells) + " |")

        if not candidates:
            lines.append(
                "| No valid repository evidence | — | — | — | — | — |"
            )

        lines += ["", "## Decision notes"]

        for item in candidates:
            lines.append(f"### {item['name']}")
            for reason in item["reasons"]:
                lines.append(f"- {reason}")

        lines += [
            "",
            "**Next step:** verify MCP, local deployment, "
            "architecture and benchmark evidence.",
        ]

        return "\n".join(lines) + "\n"