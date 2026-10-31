"""FastAPI backend. Run with:  uvicorn main:app --port 8765"""
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException

import db
from pipeline import patch_finding
from sandbox import IMAGE
from scanner import scan
from schemas import DecisionRequest, Finding, PatchRequest, PatchResponse, ScanRequest, ScanResponse
from triage import triage

app = FastAPI(title="CodeWarden")


@app.get("/health")
def health():
    docker = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
    return {
        "backend": "ok",
        "sandbox_image_ready": docker,
        "llm_configured": bool(os.environ.get("MISTRAL_API_KEY")),
    }


@app.post("/scan", response_model=ScanResponse)
def scan_files(req: ScanRequest):
    files = {clean_path(f.path): f.content for f in req.files}
    tmp = Path(tempfile.mkdtemp(prefix="codewarden-scan-"))
    try:
        for path, content in files.items():
            (tmp / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp / path).write_text(content, encoding="utf-8")
        findings = triage(scan(tmp, list(files)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    run_id = "r_" + uuid.uuid4().hex[:8]
    for f in findings:
        f.id = "f_" + uuid.uuid4().hex[:8]
        f.run_id = run_id
    db.save_run(run_id, req.project_root, files, findings)

    confirmed = [f for f in findings if f.status == "confirmed"]
    return ScanResponse(run_id=run_id, status="findings" if confirmed else "clean", findings=confirmed)


@app.post("/patch", response_model=PatchResponse)
def patch(req: PatchRequest):
    run = db.get_run(req.run_id)
    if not run:
        raise HTTPException(404, "Unknown run_id")
    data = next((f for f in run["findings"] if f["id"] == req.finding_id), None)
    if not data:
        raise HTTPException(404, "Unknown finding_id")
    finding = Finding(**data)
    original = run["files"][finding.file]
    return patch_finding(finding, run["project_root"], original, req.max_retries, req.model)


@app.post("/decision")
def decision(req: DecisionRequest):
    db.save_decision(req.finding_id, req.decision, req.reason)
    return {"ok": True}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Unknown run_id")
    run.pop("files")  # file contents are large; not needed here
    return run


def clean_path(path: str) -> str:
    """Only allow relative paths inside the project (no '..', no absolute paths)."""
    p = PurePosixPath(path.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or ":" in path:
        raise HTTPException(400, f"Bad path: {path}")
    return p.as_posix()
