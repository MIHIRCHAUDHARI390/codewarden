"""SQLite log of runs, findings, patch attempts and user decisions."""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("CODEWARDEN_DB", os.path.join(os.path.dirname(__file__), "codewarden.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, project_root TEXT, files TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, run_id TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS attempts (finding_id TEXT, attempt INTEGER, patch TEXT, verification TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS decisions (finding_id TEXT, decision TEXT, reason TEXT, created TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_run(run_id, project_root, files, findings):
    with connect() as c:
        c.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (run_id, project_root, json.dumps(files), now()))
        for f in findings:
            c.execute("INSERT INTO findings VALUES (?, ?, ?)", (f.id, run_id, f.model_dump_json()))


def get_run(run_id):
    with connect() as c:
        run = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        findings = [json.loads(r["data"]) for r in c.execute("SELECT data FROM findings WHERE run_id = ?", (run_id,))]
        ids = [f["id"] for f in findings] or [""]
        marks = ",".join("?" * len(ids))
        attempts = [dict(r) for r in c.execute(f"SELECT * FROM attempts WHERE finding_id IN ({marks})", ids)]
        decisions = [dict(r) for r in c.execute(f"SELECT * FROM decisions WHERE finding_id IN ({marks})", ids)]
    return {
        "run_id": run["id"], "project_root": run["project_root"], "created": run["created"],
        "files": json.loads(run["files"]), "findings": findings,
        "attempts": attempts, "decisions": decisions,
    }


def save_attempt(patch, verification):
    with connect() as c:
        c.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?)",
                  (patch.finding_id, patch.attempt, patch.model_dump_json(), verification.model_dump_json(), now()))


def save_decision(finding_id, decision, reason):
    with connect() as c:
        c.execute("INSERT INTO decisions VALUES (?, ?, ?, ?)", (finding_id, decision, reason, now()))
