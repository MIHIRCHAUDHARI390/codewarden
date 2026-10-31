"""Triage agent: dedupe, set severity, dismiss likely false positives, rank.

Rule-based for the MVP (deterministic and free). An LLM pass could be added later.
"""
from schemas import Finding

SEVERITY_BY_CLASS = {
    "command_injection": "critical",
    "sql_injection": "high",
    "unsafe_deserialization": "high",
    "path_traversal": "high",
    "hardcoded_secret": "medium",
    "vulnerable_dependency": "medium",
}
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def triage(findings: list[Finding]) -> list[Finding]:
    seen = set()
    result = []
    for f in findings:
        key = (f.file, f.line_start, f.vuln_class)
        if key in seen:
            continue  # same issue reported by two tools
        seen.add(key)

        f.severity = SEVERITY_BY_CLASS[f.vuln_class]
        name = f.file.rsplit("/", 1)[-1]
        if f.file.startswith("tests/") or name.startswith("test_"):
            f.status = "dismissed"
            f.triage_rationale = "Finding is in test code, not shipped code."
        else:
            f.status = "confirmed"
            f.triage_rationale = f"Reported by {f.source_tool} ({f.rule_id})."
        result.append(f)

    result.sort(key=lambda f: (f.status != "confirmed", RANK[f.severity], f.file, f.line_start))
    return result
