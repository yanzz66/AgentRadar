
"""AgentRadar local API v0.1."""

import json
import os
import threading
import uuid
import logging

logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from gpt_researcher.actions.agentradar_pipeline import (
    AgentRadarPipeline,
)

from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(
    title="AgentRadar API",
    version="0.1.0",
    description="Local AI technology intelligence and selection.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

OUTPUT_ROOT = Path(
    os.getenv("AGENTRADAR_OUTPUT_DIR", "output/agentradar/tasks")
).resolve()

MAX_WORKERS = 2
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# In-memory task registry: suitable for local MVP, not durable storage.
tasks = {}
tasks_lock = threading.Lock()


class ResearchRequest(BaseModel):
    requirement: str = Field(min_length=5, max_length=2000)
    github_query: str = Field(
        default="browser agent language:Python archived:false",
        min_length=3,
        max_length=300,
    )
    max_results: int = Field(default=8, ge=1, le=20)


class ResearchResponse(BaseModel):
    task_id: str
    status: Literal["queued", "running", "succeeded", "failed"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def execute_research(task_id: str, request: ResearchRequest):
    with tasks_lock:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["started_at"] = utc_now()

    try:
        # Each task writes to its own directory.
        task_dir = OUTPUT_ROOT / task_id
        pipeline = AgentRadarPipeline()

        summary = pipeline.run(
            requirement=request.requirement,
            github_query=request.github_query,
            max_results=request.max_results,
            output_dir=str(task_dir),
        )

        with tasks_lock:
            tasks[task_id]["status"] = "succeeded"
            tasks[task_id]["finished_at"] = utc_now()
            tasks[task_id]["summary"] = summary

    except Exception as exc:
        # Return a useful error category without exposing secrets or tracebacks.
        logger.exception(
            "AgentRadar research task %s failed",
            task_id,
        )
        with tasks_lock:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["finished_at"] = utc_now()
            tasks[task_id]["error"] = (
                f"{type(exc).__name__}: research task failed"
            )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AgentRadar API"}


@app.post(
    "/api/research",
    response_model=ResearchResponse,
    status_code=202,
)
def create_research(request: ResearchRequest):
    task_id = str(uuid.uuid4())

    with tasks_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "created_at": utc_now(),
            "request": request.model_dump(),
        }

    try:
        executor.submit(execute_research, task_id, request)
    except RuntimeError:
        with tasks_lock:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = "Task executor is unavailable"
        raise HTTPException(
            status_code=503,
            detail="Research service is unavailable",
        )

    return ResearchResponse(
        task_id=task_id,
        status="queued",
    )


@app.get("/api/research/{task_id}")
def get_research(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return dict(task)


@app.get(
    "/api/research/{task_id}/report",
    response_class=PlainTextResponse,
)
def get_report(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task["status"] != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="Research task has not succeeded",
            )

        summary = task.get("summary", {})
        report_path = summary.get("report_path")

    if not report_path:
        raise HTTPException(
            status_code=404,
            detail="Report path is unavailable",
        )

    path = Path(report_path).resolve()

    # Prevent a report path from escaping the configured output directory.
    task_root = (OUTPUT_ROOT / task_id).resolve()

    if not path.is_relative_to(task_root):
        raise HTTPException(
            status_code=403,
            detail="Invalid report path",
        )

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")

    return path.read_text(encoding="utf-8")

@app.get("/api/research/{task_id}/candidates")
def get_candidates(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)

        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        if task["status"] != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="Research task has not succeeded",
            )

        summary = task.get("summary") or {}
        candidates = summary.get("candidates")
        verification = summary.get("verification", [])

    if candidates is None:
        raise HTTPException(
            status_code=404,
            detail="Candidate data not available for this task",
        )

    return {
        "task_id": task_id,
        "candidates": candidates,
        "verification": verification,
    }


@app.get("/api/research/{task_id}/evidence")
def get_research_evidence(task_id: str):
    # 1. Confirm the task exists and is completed.
    with tasks_lock:
        task = tasks.get(task_id)

        if task is None:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        if task["status"] != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="Research task has not succeeded",
            )

    # 2. Read the evidence file from the task directory.
    # Do not trust a file path supplied by the client.
    path = OUTPUT_ROOT / task_id / "evidence.json"

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Evidence file not found",
        )

    try:
        if path.stat().st_size > 5_000_000:
            raise HTTPException(
                status_code=413,
                detail="Evidence file exceeds response limit",
            )

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail="Evidence file cannot be read",
        )

    # 3. Validate the structure from EvidenceStore.save_json().
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("evidence"), list)
        or not isinstance(data.get("claims"), list)
    ):
        raise HTTPException(
            status_code=500,
            detail="Invalid evidence file structure",
        )

    return {
        "task_id": task_id,
        "evidence": data["evidence"],
        "claims": data["claims"],
    }