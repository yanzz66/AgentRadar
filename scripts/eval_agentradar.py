
"""AgentRadar evaluation: API, evidence integrity, and runtime."""

import argparse
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

import requests


API = "http://127.0.0.1:8000"
FINAL_STATUSES = {"supported", "contradicted", "insufficient"}


def rate(valid, total):
    return round(valid / total, 4) if total else None


def assess(summary, evidence_data, report):
    """Evaluate structural integrity, not factual accuracy."""
    records = evidence_data["evidence"]
    claims = evidence_data["claims"]
    candidates = summary["candidates"]

    record_ids = [r.get("evidence_id") for r in records]
    known = set(record_ids)

    refs = [
        eid
        for claim in claims
        for eid in claim.get("evidence_ids", [])
    ]

    hashes_ok = sum(
        isinstance(r.get("content"), str)
        and r.get("content_sha256")
        == hashlib.sha256(
            r["content"].encode("utf-8")
        ).hexdigest()
        for r in records
    )

    verified_ok = sum(
        claim.get("status") in FINAL_STATUSES
        and isinstance(claim.get("verification"), dict)
        and claim["verification"].get("status") == claim["status"]
        and bool(claim["verification"].get("reason"))
        and bool(claim["verification"].get("verified_at"))
        and set(
            claim["verification"].get("evidence_ids", [])
        ) <= set(claim.get("evidence_ids", []))
        for claim in claims
    )

    candidate_refs = [
        item.get("evidence_id")
        for item in candidates
    ]

    # Evidence IDs in the Markdown comparison table.
    report_citations = set(
        re.findall(r"`([0-9a-f]{16})`", report)
    )

    failures = []

    if not records or not claims or not candidates:
        failures.append("证据、Claim 或候选项目为空")

    if len(known) != len(records) or None in known:
        failures.append("Evidence ID 缺失或重复")

    if hashes_ok != len(records):
        failures.append("存在内容哈希不一致的证据")

    if not refs or any(eid not in known for eid in refs):
        failures.append("Claim 引用了不存在的 Evidence ID")

    if verified_ok != len(claims):
        failures.append("Claim 状态与核验详情不一致")

    if any(eid not in known for eid in candidate_refs):
        failures.append("候选项目引用了不存在的 Evidence ID")

    if any(eid not in report_citations for eid in candidate_refs):
        failures.append("报告缺少候选项目的 Evidence ID")

    unknown_citations = sorted(report_citations - known)

    if unknown_citations:
        failures.append("报告引用了不存在的 Evidence ID")

    if summary.get("candidate_count") != len(candidates):
        failures.append("候选数量与运行摘要不一致")

    eligible_count = sum(
        item.get("status") == "eligible"
        for item in candidates
    )

    if summary.get("eligible_count") != eligible_count:
        failures.append("合格候选数量与运行摘要不一致")

    return {
        "structure_pass": not failures,
        "evidence_count": len(records),
        "claim_count": len(claims),
        "candidate_count": len(candidates),
        "evidence_hash_valid_rate": rate(
            hashes_ok, len(records)
        ),
        "claim_link_valid_rate": rate(
            sum(eid in known for eid in refs), len(refs)
        ),
        "claim_verification_consistency_rate": rate(
            verified_ok, len(claims)
        ),
        "candidate_evidence_coverage": rate(
            sum(eid in known for eid in candidate_refs),
            len(candidate_refs),
        ),
        "candidate_report_citation_coverage": rate(
            sum(
                eid in report_citations
                for eid in candidate_refs
            ),
            len(candidate_refs),
        ),
        "unknown_report_evidence_ids": unknown_citations,
        "failures": failures,
    }


def get_json(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_task(task_id):
    return get_json(f"{API}/api/research/{task_id}")


def main():
    parser = argparse.ArgumentParser(
        description="AgentRadar evaluation"
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--task-id",
        help="Evaluate an existing completed task",
    )
    group.add_argument(
        "--new",
        action="store_true",
        help="Run a new timed research task",
    )
    parser.add_argument("--timeout", type=int, default=600)

    args = parser.parse_args()
    elapsed = None

    if args.new:
        started = time.perf_counter()

        response = requests.post(
            f"{API}/api/research",
            json={
                "requirement": (
                    "基于 Python 开发 Browser Agent，"
                    "需要考虑本地部署和 MCP 支持，"
                    "并明确标注尚未验证的能力。"
                ),
                "github_query": (
                    "browser agent language:Python archived:false"
                ),
                "max_results": 5,
            },
            timeout=20,
        )
        response.raise_for_status()

        task_id = response.json()["task_id"]
        print("New task:", task_id, flush=True)

        while True:
            task = fetch_task(task_id)

            if task["status"] in ("succeeded", "failed"):
                break

            if time.perf_counter() - started > args.timeout:
                raise TimeoutError(
                    f"任务超时，可能仍在执行：{task_id}"
                )

            time.sleep(3)

        elapsed = round(
            time.perf_counter() - started, 2
        )

    else:
        task_id = str(uuid.UUID(args.task_id))
        task = fetch_task(task_id)

    if task["status"] != "succeeded":
        raise RuntimeError(
            f"任务未成功：{task['status']}；"
            f"{task.get('error', '无错误详情')}"
        )

    # Read the existing API results.
    candidates_data = get_json(
        f"{API}/api/research/{task_id}/candidates"
    )
    evidence_data = get_json(
        f"{API}/api/research/{task_id}/evidence"
    )

    response = requests.get(
        f"{API}/api/research/{task_id}/report",
        timeout=20,
    )
    response.raise_for_status()

    summary = {
        **task["summary"],
        "candidates": candidates_data["candidates"],
    }

    metrics = assess(
        summary,
        evidence_data,
        response.text,
    )

    metrics["task_id"] = task_id
    metrics["end_to_end_seconds"] = elapsed

    # Save evaluation artifacts.
    output = Path("output/agentradar/evaluation")
    output.mkdir(parents=True, exist_ok=True)

    json_path = output / f"{task_id}.json"
    markdown_path = output / f"{task_id}.md"

    json_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# AgentRadar 评估报告",
        "",
        f"任务 ID：`{task_id}`",
        "",
        "## 自动结构检查",
        "",
        f"结果：{'PASS' if metrics['structure_pass'] else 'FAIL'}",
        "",
        f"证据数量：{metrics['evidence_count']}",
        f"Claim 数量：{metrics['claim_count']}",
        f"候选数量：{metrics['candidate_count']}",
        f"端到端耗时（秒）：{elapsed if elapsed is not None else '未测量'}",
        "",
        "## 数据完整性",
        "",
    ]

    for key in (
        "evidence_hash_valid_rate",
        "claim_link_valid_rate",
        "claim_verification_consistency_rate",
        "candidate_evidence_coverage",
        "candidate_report_citation_coverage",
    ):
        value = metrics[key]
        lines.append(
            f"- {key}: {value if value is not None else 'N/A'}"
        )

    lines += ["", "## 自动检查发现的问题", ""]

    if metrics["failures"]:
        lines.extend(
            f"- {failure}"
            for failure in metrics["failures"]
        )
    else:
        lines.append("- 无")

    lines += [
        "",
        "## 人工质量评估",
        "",
        "- [ ] 抽查至少 3 条 GitHub 数值与原始来源一致",
        "- [ ] 没有把 Stars 当作真实用户数量",
        "- [ ] 未核验的 MCP、本地部署等能力有明确标注",
        "- [ ] 并列评分没有被解释成真实性能优劣",
        "- [ ] 报告没有包含 API Key 等敏感信息",
        "",
        "自动检查仅证明结构一致性，"
        "不代表事实准确率或模型幻觉率。",
        "",
    ]

    markdown_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        "Structure:",
        "PASS" if metrics["structure_pass"] else "FAIL",
    )
    print("Evidence:", metrics["evidence_count"])
    print("Claims:", metrics["claim_count"])
    print("Elapsed:", elapsed)
    print("Evaluation:", markdown_path)
    print("JSON:", json_path)

    if metrics["failures"]:
        print("Findings:", metrics["failures"])


if __name__ == "__main__":
    main()