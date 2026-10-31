"""Orchestrator: Patch agent -> Sandbox/Verifier -> retry with feedback (max 3 attempts)."""
import db
from patcher import PatchError, generate_patch
from schemas import Evidence, Finding, PatchResponse
from verifier import feedback, verify


def patch_finding(finding: Finding, project_root: str, original: str,
                  max_attempts: int = 3, model: str | None = None) -> PatchResponse:
    last_feedback = None
    patch = verification = None

    for attempt in range(1, max_attempts + 1):
        try:
            patch = generate_patch(finding, original, attempt, last_feedback, model, project_root)
        except PatchError as e:
            return PatchResponse(verified=False, message=str(e))

        verification = verify(finding, patch, project_root, original)
        db.save_attempt(patch, verification)

        if verification.verified:
            return PatchResponse(
                verified=True, patch=patch, verification=verification,
                evidence=Evidence(
                    finding_id=finding.id,
                    **patch.explanation.model_dump(),
                    checks_passed=[f"{k}: {v}" for k, v in verification.checks.items()],
                    verification={"verified": True, "attempt": attempt},
                ),
            )
        if verification.checks.get("patch_applies") == "file_changed_since_scan":
            return PatchResponse(verified=False, verification=verification,
                                 message="The file changed since it was scanned. Scan again.")
        last_feedback = feedback(verification, patch)

    # Escalate: explanation only, no patch offered.
    return PatchResponse(
        verified=False, verification=verification,
        message=f"No verified fix available after {max_attempts} attempts. "
                + (patch.explanation.what_was_wrong if patch else ""),
    )