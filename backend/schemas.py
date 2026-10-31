"""Data contracts from section 11 of the spec."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VulnClass = Literal[
    "hardcoded_secret",
    "sql_injection",
    "command_injection",
    "path_traversal",
    "unsafe_deserialization",
    "vulnerable_dependency",
]
Severity = Literal["low", "medium", "high", "critical"]


class Finding(BaseModel):
    # "class" is a Python keyword, so the field is vuln_class but the JSON key is "class".
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = ""
    run_id: str = ""
    file: str
    line_start: int
    line_end: int
    vuln_class: VulnClass = Field(alias="class")
    severity: Severity
    source_tool: str
    rule_id: str  # e.g. "B608"; used by the verifier to check the finding is gone
    message: str
    code_snippet: str = ""
    status: Literal["confirmed", "dismissed"] = "confirmed"
    triage_rationale: str = ""


class RegressionTest(BaseModel):
    path: str
    content: str


class Explanation(BaseModel):
    what_was_wrong: str
    why_it_matters: str
    what_changed: str


class Patch(BaseModel):
    finding_id: str
    attempt: int
    unified_diff: str
    patched_content: str  # full new file; the extension uses it for the diff view
    regression_test: Optional[RegressionTest] = None
    explanation: Explanation


class VerificationResult(BaseModel):
    finding_id: str
    attempt: int
    verified: bool
    checks: dict[str, str]
    logs: str = ""


class Evidence(BaseModel):
    finding_id: str
    what_was_wrong: str
    why_it_matters: str
    what_changed: str
    checks_passed: list[str]
    verification: dict


# ---- API request / response bodies ----

class FileIn(BaseModel):
    path: str  # relative to project_root
    content: str


class ScanRequest(BaseModel):
    project_root: str
    files: list[FileIn]


class ScanResponse(BaseModel):
    run_id: str
    status: Literal["clean", "findings"]
    findings: list[Finding]


class PatchRequest(BaseModel):
    run_id: str
    finding_id: str
    max_retries: int = 3
    model: Optional[str] = None  # override the Mistral model from the extension settings


class PatchResponse(BaseModel):
    verified: bool
    patch: Optional[Patch] = None
    verification: Optional[VerificationResult] = None
    evidence: Optional[Evidence] = None
    message: str = ""


class DecisionRequest(BaseModel):
    finding_id: str
    decision: Literal["accepted", "declined"]
    reason: Optional[str] = None
