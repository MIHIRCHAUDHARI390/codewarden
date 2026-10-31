"""Phase 4 tests: multi-agent pipeline routing and node wiring.

These tests exercise the deterministic routing logic (route_after_review,
route_after_verify) and the full graph with the Planner/Reviewer/Verifier
mocked, so no live API or Docker is required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import Explanation, Finding, Patch, VerificationResult
from pipeline import (
    PipelineState,
    route_after_review,
    route_after_verify,
    planner_node,
    review_node,
    generate_patch_node,
    verify_node,
)


def make_finding():
    return Finding(
        id="f1", file="app/db.py", line_start=3, line_end=3,
        vuln_class="sql_injection", severity="high",
        source_tool="bandit", rule_id="B608", message="SQL injection")


def make_patch():
    return Patch(
        finding_id="f1", attempt=1, unified_diff="--- a/app/db.py\n+++ b/app/db.py\n",
        patched_content="patched", regression_test=None,
        explanation=Explanation(what_was_wrong="x", why_it_matters="y", what_changed="z"))


# ---- Routing: review ----
def test_route_after_review_approved_goes_to_verify():
    state: PipelineState = {"response": None, "review_approved": True}
    assert route_after_review(state) == "verify"


def test_route_after_review_rejected_with_retries_left():
    state: PipelineState = {
        "response": None, "review_approved": False,
        "review_attempt": 1, "max_review_attempts": 3,
    }
    assert route_after_review(state) == "review_retry"


def test_route_after_review_rejected_exhausted_escalates():
    state: PipelineState = {
        "response": None, "review_approved": False,
        "review_attempt": 3, "max_review_attempts": 3,
    }
    assert route_after_review(state) == "escalate"


def test_route_after_review_error_response_ends():
    state: PipelineState = {
        "response": object(), "review_approved": True,
    }
    assert route_after_review(state) == "error_end"


# ---- Routing: verify ----
def test_route_after_verify_verified_end():
    state: PipelineState = {
        "response": None, "verification": VerificationResult(
            finding_id="f1", attempt=1, verified=True, checks={}),
    }
    assert route_after_verify(state) == "success_end"


def test_route_after_verify_file_changed_end():
    state: PipelineState = {
        "response": None, "verification": VerificationResult(
            finding_id="f1", attempt=1, verified=False,
            checks={"patch_applies": "file_changed_since_scan"}),
    }
    assert route_after_verify(state) == "file_changed_end"


def test_route_after_verify_failed_with_retries_left():
    state: PipelineState = {
        "response": None, "attempt": 1, "max_attempts": 3,
        "verification": VerificationResult(
            finding_id="f1", attempt=1, verified=False, checks={"syntax_ok": "fail"}),
    }
    assert route_after_verify(state) == "verify_retry"


def test_route_after_verify_failed_exhausted_escalates():
    state: PipelineState = {
        "response": None, "attempt": 3, "max_attempts": 3,
        "verification": VerificationResult(
            finding_id="f1", attempt=1, verified=False, checks={"syntax_ok": "fail"}),
    }
    assert route_after_verify(state) == "escalate"


def test_route_after_verify_error_response_ends():
    state: PipelineState = {
        "response": object(), "verification": VerificationResult(
            finding_id="f1", attempt=1, verified=True, checks={}),
    }
    assert route_after_verify(state) == "error_end"


# ---- Nodes ----
def test_planner_node_sets_plan(monkeypatch):
    def fake_plan(f, o, m=None):
        return {"root_cause": "r", "strategy": "s", "pitfalls": "p"}
    monkeypatch.setattr("pipeline.plan_fix", fake_plan)
    state: PipelineState = {"finding": make_finding(), "original": "orig", "model": None}
    out = planner_node(state)
    assert out["plan"]["strategy"] == "s"


def test_planner_node_fails_soft(monkeypatch):
    from planner import PlannerError
    def boom(f, o, m=None):
        raise PlannerError("down")
    monkeypatch.setattr("pipeline.plan_fix", boom)
    state: PipelineState = {"finding": make_finding(), "original": "orig", "model": None}
    out = planner_node(state)
    assert "unavailable" in out["plan"]["root_cause"]
    assert out["plan"]["strategy"] == ""


def test_review_node_increments_attempt_and_sets_approval(monkeypatch):
    monkeypatch.setattr("pipeline.review_patch", lambda f, p, o, m=None: (True, "ok"))
    state: PipelineState = {
        "finding": make_finding(), "patch": make_patch(),
        "original": "orig", "model": None, "review_attempt": 0,
    }
    out = review_node(state)
    assert out["review_attempt"] == 1
    assert out["review_approved"] is True
    assert out["review_approval_attempt"] == 1


def test_generate_patch_node_passes_plan(monkeypatch):
    captured = {}
    def fake_generate(f, o, attempt, fb, model, root, plan):
        captured["plan"] = plan
        return make_patch()
    monkeypatch.setattr("pipeline.generate_patch", fake_generate)
    state: PipelineState = {
        "finding": make_finding(), "project_root": ".", "original": "orig",
        "model": None, "attempt": 0, "last_feedback": None,
        "plan": {"strategy": "use params"},
    }
    out = generate_patch_node(state)
    assert captured["plan"]["strategy"] == "use params"
    assert out["patch"] is not None


def test_verify_node_delegates_and_increments(monkeypatch):
    def fake_verify(f, p, root, o):
        return VerificationResult(finding_id="f1", attempt=1, verified=False,
                                  checks={"a": "fail"})
    monkeypatch.setattr("pipeline.verify", fake_verify)
    monkeypatch.setattr("pipeline.db.save_attempt", lambda p, v: None)
    state: PipelineState = {
        "finding": make_finding(), "patch": make_patch(),
        "project_root": ".", "original": "orig", "verify_attempts": 2,
    }
    out = verify_node(state)
    assert out["verification"].verified is False
    assert out["verify_attempts"] == 3


# ---- Full graph: error path does not crash ----
def test_error_path_returns_stored_response(monkeypatch):
    """When the Patch agent raises PatchError, pipeline should terminate with the
    stored response and not crash in finalize_node (previously it dereferenced
    verification.verified on None)."""
    from patcher import PatchError
    from schemas import PatchResponse

    def fake_generate(*args, **kwargs):
        raise PatchError("LLM is down")
    monkeypatch.setattr("pipeline.generate_patch", fake_generate)
    monkeypatch.setattr("pipeline.plan_fix", lambda f, o, m=None: {"strategy": "s"})
    monkeypatch.setattr("pipeline.review_patch", lambda *a, **k: (False, ""))

    from pipeline import patch_finding
    resp = patch_finding(make_finding(), ".", "orig")
    assert isinstance(resp, PatchResponse)
    assert resp.verified is False
    assert "LLM is down" in resp.message


# ---- Full graph: happy path includes evidence counters ----
def test_full_pipeline_success_records_counters(monkeypatch):
    from pipeline import patch_finding

    def fake_generate(f, o, attempt, fb, model, root, plan):
        return make_patch()
    def fake_review(f, p, o, m=None):
        return True, "looks good"
    def fake_verify(f, p, root, o):
        return VerificationResult(finding_id="f1", attempt=1, verified=True,
                                  checks={"a": "pass", "b": "pass"})
    monkeypatch.setattr("pipeline.generate_patch", fake_generate)
    monkeypatch.setattr("pipeline.review_patch", fake_review)
    monkeypatch.setattr("pipeline.verify", fake_verify)
    monkeypatch.setattr("pipeline.db.save_attempt", lambda p, v: None)

    resp = patch_finding(make_finding(), ".", "orig")
    assert resp.verified is True
    assert resp.evidence is not None
    v = resp.evidence.verification
    assert v["verified"] is True
    assert v["verify_attempts"] == 1
    assert v["review_approval_attempt"] == 1
    assert v["review_attempt"] == 1
