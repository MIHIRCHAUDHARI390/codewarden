from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

VulnClass = Literal["hardcoded_secret", "sql_injection", "command_injection", "path_traversal", "unsafe_deserialization", "vulnerable_dependency"]
Severity = Literal["low", "medium", "high", "critical"]

class Finding(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str = ""
    run_id: str = ""
    file: str
    line_start: int
    line_end: int
    vuln_class: VulnClass = Field(alias="class")
    severity: Severity
    source_tool: str
    rule_id: str
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
    patched_content: str
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

#API request and response schemas
class FileIn(BaseModel):
    path: str 
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
    model: Optional[str] = None 

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