
"""AgentRadar Verification Engine v0.1.

Deterministic verification of selected GitHub metadata claims.
Unknown or unsupported claims remain insufficient.
"""

import re
from datetime import datetime, timezone


class EvidenceVerifier:
    def __init__(self, store, recent_days=90):
        self.store = store
        self.recent_days = recent_days

    @staticmethod
    def _field(content, field_name):
        """Read a simple 'Field: value' line from normalized evidence."""
        pattern = rf"(?im)^\s*{re.escape(field_name)}\s*:\s*(.*?)\s*$"
        match = re.search(pattern, content)
        return match.group(1).strip() if match else None

    @staticmethod
    def _result(status, reason, evidence_ids):
        return {
            "status": status,
            "reason": reason,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "verified_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }

    def verify_claim(self, claim):
        """Verify a Claim object against its linked evidence records."""
        evidence_ids = list(dict.fromkeys(claim.evidence_ids))
        records = [
            self.store.records[eid]
            for eid in evidence_ids
            if eid in self.store.records
        ]

        if not records:
            return self._result(
                "insufficient",
                "No available evidence is linked to this claim.",
                evidence_ids,
            )

        text = claim.text.strip()

        # Rule 1: language claims, e.g. "项目使用 Python".
        language_match = re.search(
            r"(?i)\b(?:language|programming language)\s*(?:is|:)\s*"
            r"([a-z0-9+#.-]+)\b",
            text,
        )
        if not language_match:
            language_match = re.search(
                r"(?:主要使用|使用|编程语言为|编程语言是)\s*"
                r"([A-Za-z][A-Za-z0-9+#.-]*)",
                text,
            )

        if language_match:
            expected = language_match.group(1).casefold()
            observed = [
                self._field(record.content, "Language")
                for record in records
            ]
            observed = [value for value in observed if value]

            if not observed:
                return self._result(
                    "insufficient",
                    "Linked evidence does not contain a Language field.",
                    evidence_ids,
                )

            if any(value.casefold() == expected for value in observed):
                return self._result(
                    "supported",
                    f"Evidence contains Language: {expected}.",
                    evidence_ids,
                )

            return self._result(
                "contradicted",
                f"Expected language {expected}; observed: {observed}.",
                evidence_ids,
            )

        # Rule 2: explicit Star-count claims, e.g. "Stars: 100".
        star_match = re.search(
            r"(?i)(?:stars?|star 数量|star 数|星标数)"
            r"\s*(?:is|为|是|:|：)?\s*([0-9][0-9,]*)",
            text,
        )
        if star_match:
            expected = int(star_match.group(1).replace(",", ""))
            observed = [
                self._field(record.content, "Stars")
                for record in records
            ]
            parsed = []

            for value in observed:
                if value:
                    match = re.fullmatch(r"[0-9][0-9,]*", value)
                    if match:
                        parsed.append(int(value.replace(",", "")))

            if not parsed:
                return self._result(
                    "insufficient",
                    "Linked evidence does not contain a usable Stars value.",
                    evidence_ids,
                )

            if expected in parsed:
                return self._result(
                    "supported",
                    f"Evidence contains Stars: {expected}.",
                    evidence_ids,
                )

            return self._result(
                "contradicted",
                f"Expected Stars: {expected}; observed: {parsed}.",
                evidence_ids,
            )

        # Rule 3: recent-maintenance claims.
        if any(
            phrase in text.casefold()
            for phrase in (
                "recently maintained",
                "actively maintained",
                "近期活跃",
                "活跃维护",
                "近期仍在维护",
            )
        ):
            dates = []

            for record in records:
                value = self._field(record.content, "Last pushed")
                if not value or value.casefold() == "unknown":
                    continue

                try:
                    parsed_date = datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    )
                    if parsed_date.tzinfo is None:
                        parsed_date = parsed_date.replace(
                            tzinfo=timezone.utc
                        )
                    dates.append(parsed_date.astimezone(timezone.utc))
                except ValueError:
                    continue

            if not dates:
                return self._result(
                    "insufficient",
                    "Evidence does not contain a valid Last pushed date.",
                    evidence_ids,
                )

            newest = max(dates)
            age_days = (
                datetime.now(timezone.utc) - newest
            ).total_seconds() / 86400

            if age_days < 0:
                return self._result(
                    "insufficient",
                    "The latest push date is in the future; check the source data.",
                    evidence_ids,
                )

            if age_days <= self.recent_days:
                return self._result(
                    "supported",
                    f"Latest push was {age_days:.1f} days ago; "
                    f"threshold is {self.recent_days} days.",
                    evidence_ids,
                )

            return self._result(
                "contradicted",
                f"Latest push was {age_days:.1f} days ago, "
                f"exceeding the {self.recent_days}-day threshold.",
                evidence_ids,
            )

        # Unknown claim types are never guessed.
        return self._result(
            "insufficient",
            "No verification rule supports this type of claim yet.",
            evidence_ids,
        )