
"""AgentRadar Streamlit UI v0.1."""

import requests
import streamlit as st


API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AgentRadar",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 AgentRadar")
st.caption("AI Technology Intelligence · Powered by local Qwen3:8b")

# Initialize per-session state.
defaults = {
    "task_id": None,
    "task_status": None,
    "report": None,
    "task_error": None,
    "candidates": None,
    "candidate_task_id": None,
    "candidate_error": None,
    "verification_results": [],
    "evidence_payload": None,
    "evidence_loaded_task_id": None,
    "evidence_error": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# Sidebar
with st.sidebar:
    st.header("AgentRadar")
    st.caption("Research Workspace")
    st.divider()
    st.success("Local AI · Ollama")
    st.info("Backend: FastAPI · Port 8000")


# Research form
st.header("研究任务")

with st.form("research_form"):
    requirement = st.text_area(
        "描述你的技术需求",
        value=(
            "我想基于 Python 开发 Browser Agent，"
            "比较适合本地部署和二次开发的候选项目。"
        ),
        height=120,
    )

    github_query = st.text_input(
        "GitHub 搜索条件",
        value="browser agent language:Python archived:false",
    )

    max_results = st.selectbox(
        "候选项目数量",
        [3, 5, 8, 10],
        index=1,
    )

    submitted = st.form_submit_button(
        "🚀 启动技术研究",
        type="primary",
        use_container_width=True,
    )

if submitted:
    try:
        response = requests.post(
            f"{API_BASE}/api/research",
            json={
                "requirement": requirement,
                "github_query": github_query,
                "max_results": max_results,
            },
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()

        st.session_state.task_id = data["task_id"]
        st.session_state.task_status = data["status"]
        st.session_state.report = None
        st.session_state.task_error = None

        st.session_state.candidates = None
        st.session_state.candidate_task_id = None
        st.session_state.candidate_error = None

        st.session_state.verification_results = []

        st.session_state.evidence_payload = None
        st.session_state.evidence_loaded_task_id = None
        st.session_state.evidence_error = None

        st.success(f"任务创建成功：{data['task_id']}")

    except requests.RequestException as exc:
        st.session_state.task_error = (
            f"无法创建研究任务：{type(exc).__name__}"
        )



# Task polling and report display

task_id = st.session_state.task_id
terminal = st.session_state.task_status in ("succeeded", "failed")

# Automatically poll only while the task is active.
poll_interval = "3s" if task_id and not terminal else None

if task_id:
    st.subheader("研究进度")
    st.code(task_id)


@st.fragment(run_every=poll_interval)
def poll_research():
    task_id = st.session_state.task_id

    # Critical: never poll again after a terminal state.
    if not task_id:
        return

    if st.session_state.task_status in ("succeeded", "failed"):
        return

    try:
        response = requests.get(
            f"{API_BASE}/api/research/{task_id}",
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        status = data["status"]

        if status == "queued":
            st.session_state.task_status = "queued"
            st.info("⏳ 研究任务正在排队...")
            return

        if status == "running":
            st.session_state.task_status = "running"
            st.info(
                "🔍 正在检索、核验证据并生成报告。"
                "当前后端尚未提供真实进度百分比。"
            )
            return

        if status == "succeeded":
            st.session_state.task_status = "succeeded"

            # Download the report only once.
            try:
                if st.session_state.report is None:
                    report_response = requests.get(
                        f"{API_BASE}/api/research/{task_id}/report",
                        timeout=15,
                    )
                    report_response.raise_for_status()
                    st.session_state.report = report_response.text

            except requests.RequestException as exc:
                st.session_state.task_error = (
                    f"任务已完成，但读取报告失败：{exc}"
                )

            # One full rerun; the terminal guard stops the loop.
            st.rerun()

        if status == "failed":
            st.session_state.task_status = "failed"
            st.session_state.task_error = data.get(
                "error", "研究任务执行失败"
            )
            st.rerun()

        st.warning(f"未知任务状态：{status}")

    except requests.RequestException as exc:
        st.warning(
            f"无法查询任务状态：{type(exc).__name__}。"
            "稍后会自动重试。"
        )
    except (KeyError, ValueError) as exc:
        st.error(f"任务状态响应格式异常：{exc}")


if task_id:
    poll_research()

    if st.session_state.task_status == "succeeded":
        st.success("✅ 研究任务已完成！")

    elif st.session_state.task_status == "failed":
        st.error("❌ 研究任务执行失败。")


# Display errors
if st.session_state.task_error:
    st.error(st.session_state.task_error)


# Retry loading the report without creating a new research task.
if (
    task_id
    and st.session_state.task_status == "succeeded"
    and st.session_state.report is None
):
    if st.button("重新读取报告"):
        try:
            response = requests.get(
                f"{API_BASE}/api/research/{task_id}/report",
                timeout=15,
            )
            response.raise_for_status()
            st.session_state.report = response.text
            st.session_state.task_error = None
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"读取失败：{exc}")



# Display research results: comparison + report

task_id = st.session_state.task_id

if task_id and st.session_state.task_status == "succeeded":

    # Load candidate data only once per completed task.
    if st.session_state.candidate_task_id != task_id:
        try:
            response = requests.get(
                f"{API_BASE}/api/research/{task_id}/candidates",
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()

            candidates = payload["candidates"]
            if not isinstance(candidates, list):
                raise ValueError("Invalid candidates payload")

            st.session_state.candidates = candidates
            st.session_state.verification_results = payload.get(
                "verification", []
            )
            st.session_state.candidate_error = None

        except (requests.RequestException, ValueError, KeyError) as exc:
            st.session_state.candidate_error = (
                f"候选项目加载失败：{exc}"
            )
            st.session_state.candidates = []

        finally:
            # Prevent repeated GET requests on every rerun.
            st.session_state.candidate_task_id = task_id

    st.divider()
    st.header("📊 AgentRadar 研究结果")

    comparison_tab, evidence_tab, report_tab = st.tabs([
        "候选项目对比",
        "证据追踪",
        "完整研究报告",
    ])

    with comparison_tab:
        if st.session_state.candidate_error:
            st.error(st.session_state.candidate_error)

            if st.button("重新加载候选项目"):
                st.session_state.candidate_task_id = None
                st.rerun()

        candidates = st.session_state.candidates or []

        if candidates:
            eligible_count = sum(
                item["status"] == "eligible"
                for item in candidates
            )

            col1, col2, col3 = st.columns(3)

            col1.metric("候选总数", len(candidates))
            col2.metric("元数据符合", eligible_count)
            col3.metric(
                "需要补充资料",
                sum(
                    item["status"] == "needs_review"
                    for item in candidates
                ),
            )

            status_names = {
                "eligible": "元数据符合",
                "excluded": "硬性排除",
                "needs_review": "资料待补",
            }

            verification_map = {
                item["evidence_id"]: item["status"]
                for item in st.session_state.verification_results
            }

            verification_names = {
                "supported": "支持",
                "contradicted": "冲突",
                "insufficient": "证据不足",
            }

            table_rows = []

            for item in candidates:
                verification_status = verification_map.get(
                    item["evidence_id"]
                )

                table_rows.append({
                    "项目": item["name"],
                    "状态": status_names.get(
                        item["status"], item["status"]
                    ),
                    "评分": item["score"],
                    "Stars": item["stars"],
                    "主要语言": item["language"],
                    "许可证": item["license"],
                    "最近推送（天）": item["days_since_push"],
                    "Python语言核验": verification_names.get(
                        verification_status, "未核验"
                    ),
                    "GitHub": item["url"],
                })

            st.dataframe(
                table_rows,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "GitHub": st.column_config.LinkColumn(
                        "GitHub 仓库"
                    ),
                    "评分": st.column_config.NumberColumn(
                        "元数据评分",
                        format="%d",
                    ),
                },
            )

            st.caption(
                "注意：评分基于维护时间、Stars 和许可证元数据。"
                "Python语言核验不等于完成了所有技术能力核验。"
            )

            st.subheader("查看项目评分详情")

            selected_index = st.selectbox(
                "选择候选项目",
                options=list(range(len(candidates))),
                format_func=lambda i: candidates[i]["name"],
            )

            selected = candidates[selected_index]

            st.write("**项目名称：**", selected["name"])
            st.write("**当前状态：**", status_names.get(
                selected["status"], selected["status"]
            ))
            st.write("**Evidence ID：**")
            st.code(selected["evidence_id"])

            st.markdown("**评分与筛选依据：**")

            for reason in selected["reasons"]:
                st.markdown(f"- {reason}")

            st.link_button(
                "🔗 打开 GitHub 仓库",
                selected["url"],
            )

        elif not st.session_state.candidate_error:
            st.info("本次研究没有可展示的候选项目。")

    with evidence_tab:
        st.subheader("🔎 Evidence Explorer")
        st.caption("查看原始来源、证据快照和关联的核验结论。")

        # Fetch once per completed task.
        if st.session_state.evidence_loaded_task_id != task_id:
            try:
                response = requests.get(
                    f"{API_BASE}/api/research/{task_id}/evidence",
                    timeout=15,
                )
                response.raise_for_status()

                payload = response.json()

                if (
                        not isinstance(payload, dict)
                        or not isinstance(payload.get("evidence"), list)
                        or not isinstance(payload.get("claims"), list)
                ):
                    raise ValueError("Invalid evidence response")

                st.session_state.evidence_payload = payload
                st.session_state.evidence_error = None

            except (requests.RequestException, ValueError) as exc:
                st.session_state.evidence_payload = None
                st.session_state.evidence_error = str(exc)

            st.session_state.evidence_loaded_task_id = task_id

        if st.session_state.evidence_error:
            st.error(st.session_state.evidence_error)

            if st.button("重新加载证据"):
                st.session_state.evidence_loaded_task_id = None
                st.rerun()

        payload = st.session_state.evidence_payload

        if payload:
            records = payload["evidence"]
            claims = payload["claims"]

            col1, col2 = st.columns(2)
            col1.metric("已保存证据", len(records))
            col2.metric("已记录 Claim", len(claims))

            if records:
                index = st.selectbox(
                    "选择要查看的证据",
                    options=list(range(len(records))),
                    format_func=lambda i: (
                        f"{records[i].get('title', 'Unknown')} "
                        f"· {records[i].get('source', 'Unknown')}"
                    ),
                    key=f"evidence_select_{task_id}",
                )

                record = records[index]
                evidence_id = record.get("evidence_id", "")

                st.divider()
                st.markdown("#### 证据基本信息")

                st.write("**标题：**", record.get("title", "Unknown"))
                st.write("**来源：**", record.get("source", "Unknown"))
                st.write(
                    "**采集时间：**",
                    record.get("retrieved_at", "Unknown"),
                )
                st.write(
                    "**内容类型：**",
                    record.get("content_kind", "Unknown"),
                )
                st.write("**Evidence ID：**")
                st.code(evidence_id)

                url = record.get("url", "")
                if isinstance(url, str) and url.startswith(
                        ("https://", "http://")
                ):
                    st.link_button("打开原始证据来源", url)

                st.markdown("#### 保存的证据快照")
                st.code(
                    record.get("content", ""),
                    language="text",
                )

                # Find claims linked to this Evidence ID.
                linked_claims = [
                    claim
                    for claim in claims
                    if evidence_id in claim.get("evidence_ids", [])
                ]

                st.markdown("#### 关联的核验结论")

                if not linked_claims:
                    st.info("当前没有与该证据直接关联的 Claim。")

                for claim in linked_claims:
                    with st.expander(
                            claim.get("text", "Unnamed claim"),
                            expanded=True,
                    ):
                        st.write(
                            "**核验状态：**",
                            claim.get("status", "unverified"),
                        )

                        verification = claim.get("verification")

                        if isinstance(verification, dict):
                            st.write(
                                "**判断理由：**",
                                verification.get(
                                    "reason", "No reason recorded"
                                ),
                            )
                            st.write(
                                "**核验时间：**",
                                verification.get(
                                    "verified_at", "Unknown"
                                ),
                            )

                            st.write(
                                "**核验引用：**",
                                verification.get(
                                    "evidence_ids", []
                                ),
                            )

            else:
                st.info("本次研究没有保存证据记录.")

        st.caption(
            "supported 表示当前规则核验支持该结论，"
            "不等于已完成所有技术能力或事实的全面验证。"
        )

    with report_tab:
        if st.session_state.report is not None:
            st.download_button(
                "⬇️ 下载 Markdown 报告",
                data=st.session_state.report,
                file_name="agentradar_report.md",
                mime="text/markdown",
            )

            st.markdown(st.session_state.report)

        else:
            st.info(
                "研究任务已完成，但报告尚未加载。"
                "请使用页面上方的重新读取报告功能。"
            )