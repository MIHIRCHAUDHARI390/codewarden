"""Orchestrator: LangGraph state machine -- Patch agent -> Sandbox/Verifier -> retry with feedback.

Nodes:
  generate_patch  — scalls the Patch agent (Mistral LLM)
  verify           — runs the deterministic Verifier in Docker
  escalate          — sbuilds the "no verified fix" response

Conditional edges after verify:
  verified                 – END (return success)
  file_changed_since_scan – END (stop, file changed)
  retries remaining     — sgenerate_patch (retry with feedback)
  no retries left       — sescalate → END (explanation only)
"""
import os
from typing import TypedDict

import db
from langgraph.graph import END, StateGraph
from patcher import PatchError, generate_patch
from schemas import Evidence, Finding, Patch, PatchResponse, VerificationResult
from verifier import feedback, verify


class PipelineState(TypedDict, total=False):
    finding: Finding
    project_root: str
    original: str
    model: str | None
    max_attempts: int
    attempt: int
    patch: Patch | None
    verification: VerificationResult | None
    last_feedback: dict | None
    response: PatchResponse | None


def generate_patch_node(state: PipelineState) -> dict:
    """Call the Patch agent. On PatchError, set response and signal end."""
    finding = state["finding"]
    attempt = state.get("attempt", 0) + 1
    project_root = state["project_root"]
    original = state["original"]
    model = state.get("model")
    last_feedback = state.get("last_feedback")

    try:
        patch = generate_patch(finding, original, attempt, last_feedback, model, project_root)
    except PatchError as e:
        return {"attempt": attempt, "response": PatchResponse(verified=False, message=str(e))}

    return {"attempt": attempt, "patch": patch, "response": None}


def verify_node(state: PipelineState) -> dict:
    """Run the deterministic verifier in the sandbox."""
    finding = state["finding"]
    patch = state["patch"]
    project_root = state["project_root"]
    original = state["original"]

    verification = verify(finding, patch, project_root, original)
    db.save_attempt(patch, verification)
    return {"verification": verification}


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


def route_after_verify(state: PipelineState) -> str:
    """Conditional edge: decide what to do after verification."""
    if state.get("response") is not None:
        return "end"  # generate_patch failed

    verification = state["verification"]
    if verification.verified:
        return "end"  # success – build response in finalize
    if verification.checks.get("patch_applies") == "file_changed_since_scan":
        return "end"  # file changed – stop
    if state["attempt"] < state.get("max_attempts", 3):
        return "retry"  # retries left — generate_patch with feedback
    return "escalate" # no retries – escalate


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
                checks_passed=[f"{k: v}" for k, v in verification.checks.items()],
                verification={"verified": True, "attempt": attempt},
            ),
    )}
    # file_changed_since_scan
    return {"response": PatchResponse(
        verified=False, verification=verification,
        message="The file changed since it was scanned. Scan again.",
    )}


def prepare_retry_node(state: PipelineState) -> dict:
    """Prepare feedback for the next retry attempt."""
    v = state["verification"]
    p = state["patch"]
    return {"last_feedback": feedback(v, p)}


# ---- Build the graph ----
def _build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("generate_patch", generate_patch_node)
    graph.add_node("verify", verify_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("prepare_retry", prepare_retry_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("generate_patch")
    graph.add_edge("generate_patch", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {
        "end": "finalize",
        "retry": "prepare_retry",
        "escalate": "escalate",
    })
    graph.add_edge("prepare_retry", "generate_patch")
    graph.add_edge("finalize", END)
    graph.add_edge("escalate", END)

    return graph.compile()


# Module-level compiled graph (reused across calls)
_compiled_graph = _build_graph()


# ---- Public API ----
def patch_finding(finding: Finding, project_root: str, original: str,
                       max_attempts: int = 3, model: str | None = None) -> PatchResponse:
    """Run the LangGraph pipeline and return a PatchResponse."""
    initial_state: PipelineState = {
        "finding": finding,
        "project_root": project_root,
        "original": original,
        "model": model,
        "max_attempts": max_attempts,
        "attempt": 0,
        "patch": None,
        "verification": None,
        "last_feedback": None,
        "response": None,
    }

    result = _compiled_graph.invoke(initial_state)
    return result["response"]


def get_pipeline_graph_ascii() -> str:
    "Return an ASCII representation of the LangGraph state machine."""
    return _compiled_graph.get_graph().draw_ascii()


def get_pipeline_graph_mermaid() -> str:
    """Return a Mermaid diagram of the LangGraph state machine."""
    return _compiled_graph.get_graph().draw_mermaid()
