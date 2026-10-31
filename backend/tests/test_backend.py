"""Backend tests. Run from backend/:  python -m pytest -q
The Docker tests need the sandbox image:  docker build -t codewarden-sandbox -f Dockerfile.sandbox .
"""
import subprocess
from pathlib import Path

import pytest

import patcher
from patcher import generate_patch, redact, unredact
from pipeline import patch_finding
from scanner import scan
from schemas import Finding
from triage import triage
from verifier import verify

DEMO = Path(__file__).resolve().parents[2] / "demo_apps" / "vulnapp"
needs_docker = pytest.mark.skipif(
    subprocess.run(["docker", "image", "inspect", "codewarden-sandbox"], capture_output=True).returncode != 0,
    reason="sandbox image not built",
)

GOOD_SQL_FIX = '''import sqlite3


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (name TEXT, email TEXT)")
    conn.execute("INSERT INTO users VALUES ('alice', 'alice@example.com')")
    conn.execute("INSERT INTO users VALUES ('bob', 'bob@example.com')")
    return conn


def find_user(conn, name):
    query = "SELECT name, email FROM users WHERE name = ?"
    return conn.execute(query, (name,)).fetchall()
'''

SQL_EXPLOIT_TEST = '''from app import db


def test_injection_returns_no_extra_rows():
    conn = db.make_db()
    assert db.find_user(conn, "' OR '1'='1") == []
'''


def sql_finding():
    f = next(f for f in scan(DEMO, ["app/db.py"]) if f.vuln_class == "sql_injection")
    f.id = "f_test"
    return f


def fake_llm(patched_file, test_code=SQL_EXPLOIT_TEST):
    return lambda prompt, model: {
        "patched_file": patched_file, "test_code": test_code,
        "what_was_wrong": "w", "why_it_matters": "m", "what_changed": "c",
    }


def test_scanner_finds_every_code_class():
    files = [p.relative_to(DEMO).as_posix() for p in DEMO.rglob("*.py")]
    classes = {f.vuln_class for f in scan(DEMO, files)}
    assert classes >= {"sql_injection", "command_injection", "path_traversal",
                       "unsafe_deserialization", "hardcoded_secret"}


def test_triage_dedupes_and_dismisses_test_code():
    def make(file, tool):
        return Finding(file=file, line_start=3, line_end=3, vuln_class="sql_injection", severity="low",
                       source_tool=tool, rule_id="B608", message="m")
    out = triage([make("app/a.py", "bandit"), make("app/a.py", "semgrep"), make("tests/test_a.py", "bandit")])
    assert len(out) == 2
    assert out[0].status == "confirmed" and out[0].severity == "high"
    assert out[1].status == "dismissed"


def test_secrets_are_redacted_before_sending():
    src = 'API_TOKEN = "demo-4f9a8b7c6d5e4f3a2b1c"\n'
    hidden, secrets = redact(src)
    assert "demo-4f9a" not in hidden
    assert unredact(hidden, secrets) == src


@needs_docker
def test_good_patch_is_verified(monkeypatch):
    monkeypatch.setattr(patcher, "call_llm", fake_llm(GOOD_SQL_FIX))
    f = sql_finding()
    original = (DEMO / f.file).read_text()
    v = verify(f, generate_patch(f, original, 1, []), str(DEMO), original)
    assert v.verified, v.checks


@needs_docker
def test_patch_that_breaks_existing_tests_is_rejected(monkeypatch):
    broken = GOOD_SQL_FIX.replace("return conn.execute(query, (name,)).fetchall()", "return []")
    monkeypatch.setattr(patcher, "call_llm", fake_llm(broken))
    f = sql_finding()
    original = (DEMO / f.file).read_text()
    v = verify(f, generate_patch(f, original, 1, []), str(DEMO), original)
    assert not v.verified
    assert v.checks["existing_tests"] == "fail"


@needs_docker
def test_retry_loop_uses_verifier_feedback(monkeypatch, tmp_path):
    monkeypatch.setattr("db.DB_PATH", str(tmp_path / "t.db"))
    answers = iter([GOOD_SQL_FIX.replace("(name,)", "()"), GOOD_SQL_FIX])  # 1st attempt is wrong
    prompts = []

    def llm(prompt, model):
        prompts.append(prompt)
        return fake_llm(next(answers))(prompt, model)

    monkeypatch.setattr(patcher, "call_llm", llm)
    f = sql_finding()
    res = patch_finding(f, str(DEMO), (DEMO / f.file).read_text())
    assert res.verified and res.patch.attempt == 2
    assert "rejected by the verifier" in prompts[1]


@needs_docker
def test_dependency_bump_is_verified():
    f = Finding(file="requirements.txt", line_start=2, line_end=2, vuln_class="vulnerable_dependency",
                severity="high", source_tool="pip-audit", rule_id="DEP:pyyaml", id="f_dep",
                message="pyyaml 5.3.1 has known vulnerabilities: X. Fixed in 5.4.")
    original = (DEMO / "requirements.txt").read_text()
    p = generate_patch(f, original, 1, [])
    assert "pyyaml==5.4" in p.patched_content
    v = verify(f, p, str(DEMO), original)
    assert v.verified, v.checks
