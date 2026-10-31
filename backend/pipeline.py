"""Orchestrator: LangGraph state machine -- multi-agent patch pipeline.

Agents (in order):
  Planner agent  (planner.py)    -- analyses the finding, proposes a strategy
  Patch agent    (patcher.py)    -- generates a candidate fix + regression test
  Reviewer agent (reviewer.py)   -- independently critiques the patch (LLM)
  Verifier      (verifier.py)    -- deterministic 7-check gate in Docker

Flow:
  planner -> generate_patch -> review -> verify -> finalize
                 | (critique) -> generate_patch (review retry)
                 + (approve) -> verify
  verify retries -> generate_patch with verifier feedback (up to max_attempts)

Nodes:
  planner         -- Planner agent (Mistral LLM)
  generate_patch  -- Patch agent (Mistral LLM)
  review          -- Reviewer agent (Mistral LLM)
  verify          -- deterministic Verifier in Docker
  escalate        -- builds the "no verified fix" response

Conditional edges after review:
  approved                 -> verify
  review retries remaining -> generate_patch (critique retry)
  no review retries left   -> escalate
  error (response set)     -> END (return the stored response directly)

Conditional edges after verify:
  verified                 -> finalize (return success)
  file_changed_since_scan  -> finalize (stop, file changed)
  verify retries remaining -> generate_patch (retry with feedback)
  no retries left          -> escalate
"""
from typing import TypedDict

import db
from langgraph.graph import END, StateGraph
from patcher import PatchError, generate_patch
from planner import PlannerError, plan_fix
from reviewer import ReviewerError, review_patch
from schemas import Evidence, Finding, Patch, PatchResponse, VerificationResult
from verifier import feedback, verify


class PipelineState(TypedDict, total=False):
    finding: Finding
    project_root: str
    original: str
    model: str | None
    max_attempts: int
    attempt: int
    max_review_attempts: int
    review_attempt: int
    review_approved: bool | None
    review_approval_attempt: int | None
    verify_attempts: int
    plan: dict[str, str] | None
    patch: Patch | None
    verification: VerificationResult | None
    last_feedback: dict | None
    response: PatchResponse | None


def planner_node(state: PipelineState) -> dict:
    """Call the Planner agent to analyse the finding before patching.

    Fails soft: if the Planner is unreachable we continue without a strategy so
    the rest of the pipeline can still run.
    """
    finding = state["finding"]
    original = state["original"]
    model = state.get("model")
    try:
        plan = plan_fix(finding, original, model)
    except PlannerError as e:
        plan = {"root_cause": f"Planner unavailable: {e}",
                "strategy": "", "pitfalls": ""}
    return {"plan": plan}


def generate_patch_node(state: PipelineState) -> dict:
    """Call the Patch agent. On PatchError, set response and signal end."""
    finding = state["finding"]
    attempt = state.get("attempt", 0) + 1
    project_root = state["project_root"]
    original = state["original"]
    model = state.get("model")
    last_feedback = state.get("last_feedback")
    plan = state.get("plan")

    try:
        patch = generate_patch(finding, original, attempt, last_feedback, model,
                               project_root, plan)
    except PatchError as e:
        return {"attempt": attempt, "response": PatchResponse(verified=False, message=str(e))}
    return {"attempt": attempt, "patch": patch, "response": None}


def review_node(state: PipelineState) -> dict:
    """Call the Reviewer agent to critique the generated patch."""
    finding = state["finding"]
    patch = state.get("patch")
    original = state["original"]
    model = state.get("model")
    review_attempt = state.get("review_attempt", 0) + 1

    if patch is None:
        return {"review_attempt": review_attempt, "review_approved": False}

    try:
        approved, critique = review_patch(finding, patch, original, model)
    except ReviewerError as e:
        # Reviewer unavailable: fail safe -- do not approve, surface the error.
        return {
            "review_attempt": review_attempt,
            "review_approved": False,
            "response": PatchResponse(verified=False, message=f"Reviewer error: {e}"),
        }

    out = {"review_attempt": review_attempt, "review_approved": approved,
           "last_feedback": {"critique": critique, "reviewer": "review_agent"}}
    if approved:
        out["review_approval_attempt"] = review_attempt
    return out


def verify_node(state: PipelineState) -> dict:
    """Run the deterministic verifier in the sandbox."""
    finding = state["finding"]
    patch = state["patch"]
    project_root = state["project_root"]
    original = state["original"]

    verification = verify(finding, patch, project_root, original)
    db.save_attempt(patch, verification)
    return {"verification": verification,
            "verify_attempts": state.get("verify_attempts", 0) + 1}


def escalate_node(state: PipelineState) -> dict:
    """Build the 'no verified fix' response (explanation only)."""
    patch = state.get("patch")
    verification = state.get("verification")
    max_attempts = state.get("max_attempts", 3)
    msg = f"No verified fix available after {max_attempts} attempts. "
    if patch:
        msg += patch.explanation.what_was_wrong
    return {"response": PatchResponse(
        verified=False, verification=verification, message=msg,
    )}


def route_after_review(state: PipelineState) -> str:
    """Conditional edge: decide what to do after the Reviewer agent."""
    if state.get("response") is not None:
        return "error_end"  # generate_patch / review failed — return stored response
    if state.get("review_approved"):
        return "verify"
    if state.get("review_attempt", 0) < state.get("max_review_attempts", 2):
        return "review_retry"  # critique retry — generate_patch with reviewer feedback
    return "escalate"


def route_after_verify(state: PipelineState) -> str:
    """Conditional edge: decide what to do after verification."""
    if state.get("response") is not None:
        return "error_end"  # defensive — return stored response directly

    verification = state["verification"]
    if verification.verified:
        return "success_end"  # success – build response in finalize
    if verification.checks.get("patch_applies") == "file_changed_since_scan":
        return "file_changed_end"  # file changed – stop
    if state["attempt"] < state.get("max_attempts", 3):
        return "verify_retry"  # retries left — generate_patch with feedback
    return "escalate"  # no retries – escalate


def finalize_node(state: PipelineState) -> dict:
    """Build the success or file_changed_since_scan response after verify."""
    finding = state["finding"]
    patch = state["patch"]
    verification = state["verification"]
    attempt = state["attempt"]

    if verification.verified:
        return {"response": PatchResponse(
            verified=True, patch=patch, verification=verification,
            evidence=Evidence(
                finding_id=finding.id,
                **patch.explanation.model_dump(),
                checks_passed=[f"{k}: {v}" for k, v in verification.checks.items()],
                verification={
                    "verified": True,
                    "attempt": attempt,
                    "review_attempt": state.get("review_attempt", 0),
                    "review_approval_attempt": state.get("review_approval_attempt"),
                    "verify_attempts": state.get("verify_attempts", 0),
                },
            ),
    )}
    # file_changed_since_scan
    return {"response": PatchResponse(
        verified=False, verification=verification,
        message="The file changed since it was scanned. Scan again.",
    )}


def prepare_retry_node(state: PipelineState) -> dict:
    """Prepare verifier feedback for the next generate_patch attempt."""
    v = state["verification"]
    p = state["patch"]
    return {"last_feedback": feedback(v, p)}


def prepare_review_retry_node(state: PipelineState) -> dict:
    """Pass the Reviewer's critique to the Patch agent for the next attempt."""
    p = state.get("patch")
    critique = state.get("last_feedback", {}).get("critique", "")
    return {"last_feedback": {
        "failed_checks": {"review": "rejected"},
        "reviewer_critique": critique,
        "your_previous_diff": p.unified_diff if p else "",
        "log_tail": "Reviewer rejected the patch before verification.",
    }}


# ---- Build the graph ----
def _build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("planner", planner_node)
    graph.add_node("generate_patch", generate_patch_node)
    graph.add_node("review", review_node)
    graph.add_node("verify", verify_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("prepare_retry", prepare_retry_node)
    graph.add_node("prepare_review_retry", prepare_review_retry_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "generate_patch")
    graph.add_edge("generate_patch", "review")
    graph.add_conditional_edges("review", route_after_review, {
        "verify": "verify",
        "review_retry": "prepare_review_retry",
        "escalate": "escalate",
        "error_end": END,
    })
    graph.add_edge("prepare_review_retry", "generate_patch")
    graph.add_conditional_edges("verify", route_after_verify, {
        "success_end": "finalize",
        "file_changed_end": "finalize",
        "verify_retry": "prepare_retry",
        "escalate": "escalate",
        "error_end": END,
    })
    graph.add_edge("prepare_retry", "generate_patch")
    graph.add_edge("finalize", END)
    graph.add_edge("escalate", END)

    return graph.compile()


# Module-level compiled graph (reused across calls)
_compiled_graph = _build_graph()


# ---- Public API ----
def patch_finding(finding: Finding, project_root: str, original: str,
                  max_attempts: int = 3, model: str | None = None,
                  max_review_attempts: int = 2) -> PatchResponse:
    """Run the multi-agent LangGraph pipeline and return a PatchResponse."""
    initial_state: PipelineState = {
        "finding": finding,
        "project_root": project_root,
        "original": original,
        "model": model,
        "max_attempts": max_attempts,
        "attempt": 0,
        "max_review_attempts": max_review_attempts,
        "review_attempt": 0,
        "review_approved": None,
        "review_approval_attempt": None,
        "verify_attempts": 0,
        "plan": None,
        "patch": None,
        "verification": None,
        "last_feedback": None,
        "response": None,
    }

    result = _compiled_graph.invoke(initial_state)
    return result["response"]


def get_pipeline_graph_ascii() -> str:
    """Return an ASCII representation of the multi-agent LangGraph state machine."""
    return _compiled_graph.get_graph().draw_ascii()


def get_pipeline_graph_mermaid() -> str:
    """Return a Mermaid diagram of the multi-agent LangGraph state machine."""
    return _compiled_graph.get_graph().draw_mermaid()
