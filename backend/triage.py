"""Triage agent: dedupe, set severity, dismiss likely false positives, rank.

Rule-based for dedupe/severity/ranking (deterministic and free).
LLM pass for logic-level false-positive detection and exploitability scoring.
"""
import json
import os
import time
from pathlib import Path

import httpx

from schemas import Finding

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

SEVERITY_BY_CLASS = {
    "command_injection": "critical",
    "sql_injection": "high",
    "unsafe_deserialization": "high",
    "path_traversal": "high",
    "hardcoded_secret": "medium",
    "vulnerable_dependency": "medium",
}
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

TRIAGE_SYSTEM_PROMPT = """You are a security triage agent. Given a finding and surrounding code context,
decide if it is a real vulnerability or a false positive.

Consider:
- Is the input a constant or hardcoded value (not user-controlled)?
- Is the value sanitized or validated upstream?
- Is this in test/demo code that doesn't ship?
- Is the function actually reachable from an entry point?

Return JSON only:
{"is_real": true/false, "exploitability": "low/medium/high", "rationale": "one sentence explanation"}"""


def triage(findings: list[Finding], project_root: str = "", model: str | None = None) -> list[Finding]:
    """Dedupe, set severity, dismiss test-code findings, LLM triage pass, rank by severity."""
    seen = set()
    result = []
    for f in findings:
        key = (f.file, f.line_start, f.vuln_class)
        if key in seen:
            continue
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

    confirmed = [f for f in result if f.status == "confirmed"]
    if confirmed and project_root:
        llm_triage_pass(confirmed, project_root, model)

    result.sort(key=lambda f: (f.status != "confirmed", RANK[f.severity], f.file, f.line_start))
    return result


def llm_triage_pass(findings: list[Finding], project_root: str, model: str | None = None) -> None:
    """Use Mistral to assess exploitability and filter false positives."""
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        return  

    model = model or os.environ.get("CODEWARDEN_MODEL", "codestral-latest")

    for f in findings:
        try:
            file_path = Path(project_root) / f.file
            lines = file_path.read_text(encoding="utf-8").splitlines()
            start = max(0, f.line_start - 5)
            end = min(len(lines), f.line_end + 5)
            context = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
        except (FileNotFoundError, OSError):
            context = f.code_snippet

        prompt = (
            f"Finding: {f.vuln_class} in {f.file} (lines {f.line_start}-{f.line_end})\n"
            f"Rule: {f.rule_id}\n"
            f"Message: {f.message}\n"
            f"Code snippet: {f.code_snippet}\n\n"
            f"Surrounding code:\n{context}\n\n"
            "Is this a real vulnerability or a false positive?"
        )

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            for wait in (2, 5, 10, 0):
                response = httpx.post(
                    MISTRAL_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                    timeout=60,
                )
                if response.status_code != 429 or not wait:
                    break
                time.sleep(wait)

            if response.status_code != 200:
                continue

            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)

            if not data.get("is_real", True):
                f.status = "dismissed"
                f.triage_rationale = f"LLM triage: false positive — {data.get('rationale', '')}"
            else:
                f.status = "confirmed"
                exploitability = data.get("exploitability", "medium")
                f.triage_rationale = (
                    f"LLM triage: real vulnerability (exploitability={exploitability}) — "
                    f"{data.get('rationale', '')}"
                )
                if exploitability == "high" and f.severity in ("low", "medium"):
                    f.severity = "high"
        except (json.JSONDecodeError, KeyError, httpx.HTTPError, Exception):
            continue  
