"""Scanner agent: runs static tools and turns their output into Finding objects.

Tools: Bandit (SQLi, command injection, deserialization, passwords),
a regex secret detector, a small AST rule for path traversal, and pip-audit.
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

from packaging.version import Version

from schemas import Finding

# Bandit test id -> our vulnerability class
BANDIT_MAP = {
    "B608": "sql_injection",
    "B602": "command_injection",
    "B604": "command_injection",
    "B605": "command_injection",
    "B609": "command_injection",
    "B301": "unsafe_deserialization",
    "B302": "unsafe_deserialization",
    "B506": "unsafe_deserialization",
    "B105": "hardcoded_secret",
    "B106": "hardcoded_secret",
    "B107": "hardcoded_secret",
}

SECRET_PATTERNS = [
    # name = "long literal", e.g. API_KEY = "abcd1234..."
    re.compile(r"""(?i)\b\w*(api_?key|secret|token|passw(or)?d|access_?key)\w*\s*=\s*["']([^"']{8,})["']"""),
    re.compile(r"""["'](AKIA[0-9A-Z]{16})["']"""),       # AWS access key id
    re.compile(r"""["'](ghp_[A-Za-z0-9]{36})["']"""),     # GitHub token
    re.compile(r"""["'](sk-[A-Za-z0-9_-]{20,})["']"""),   # generic "sk-" API keys
]

# If a function calls one of these, we assume it checks the path.
PATH_GUARDS = ("resolve(", "realpath(", "abspath(", "is_relative_to(", "commonpath(")


def scan(root: Path, files: list[str]) -> list[Finding]:
    """Scan the given files (paths relative to root)."""
    py_files = [f for f in files if f.endswith(".py")]
    findings = []
    if py_files:
        findings += run_bandit(root, py_files)
        for f in py_files:
            text = (root / f).read_text(encoding="utf-8")
            findings += find_secrets(f, text)
            findings += find_path_traversal(f, text)
    if "requirements.txt" in files:
        findings += run_pip_audit(root)
    return findings


def run_bandit(root: Path, files: list[str]) -> list[Finding]:
    proc = subprocess.run(
        [sys.executable, "-m", "bandit", "-f", "json", "-q", *files],
        cwd=root, capture_output=True, text=True,
    )
    data = json.loads(proc.stdout or "{}")
    findings = []
    for r in data.get("results", []):
        vuln_class = BANDIT_MAP.get(r["test_id"])
        if not vuln_class:
            continue  # not one of our 6 classes
        lines = r.get("line_range") or [r["line_number"]]
        findings.append(Finding(
            file=Path(r["filename"]).as_posix(),
            line_start=lines[0],
            line_end=lines[-1],
            vuln_class=vuln_class,
            severity=r["issue_severity"].lower(),
            source_tool="bandit",
            rule_id=r["test_id"],
            message=r["issue_text"],
            code_snippet=r.get("code", "").strip(),
        ))
    return findings


def find_secrets(file: str, text: str) -> list[Finding]:
    findings = []
    for n, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#") or "environ" in line or "getenv" in line:
            continue
        if any(p.search(line) for p in SECRET_PATTERNS):
            findings.append(Finding(
                file=file, line_start=n, line_end=n,
                vuln_class="hardcoded_secret", severity="high",
                source_tool="secret-regex", rule_id="SECRET",
                message="Hardcoded secret or API key",
                code_snippet=line.strip(),
            ))
    return findings


def find_path_traversal(file: str, text: str) -> list[Finding]:
    """Flag open(os.path.join(BASE, x)) / open(BASE + x) / open(f"..{x}")
    inside a function that never checks the resulting path."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body_src = ast.get_source_segment(text, func) or ""
        if any(g in body_src for g in PATH_GUARDS):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and _is_open(node) and node.args and _is_built_path(node.args[0]):
                findings.append(Finding(
                    file=file, line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                    vuln_class="path_traversal", severity="high",
                    source_tool="path-rule", rule_id="PATH",
                    message="File path built from input without checking it stays inside the base folder",
                    code_snippet=ast.get_source_segment(text, node) or "",
                ))
    return findings


def _is_open(call: ast.Call) -> bool:
    f = call.func
    return (isinstance(f, ast.Name) and f.id == "open") or (isinstance(f, ast.Attribute) and f.attr in ("open", "send_file"))


def _is_built_path(arg: ast.expr) -> bool:
    if isinstance(arg, (ast.BinOp, ast.JoinedStr)):
        return True
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "join":
        return any(not isinstance(a, ast.Constant) for a in arg.args)
    return False


def run_pip_audit(root: Path) -> list[Finding]:
    req = root / "requirements.txt"
    proc = subprocess.run(
        [sys.executable, "-m", "pip_audit", "-r", str(req), "--no-deps", "--disable-pip",
         "-f", "json", "--progress-spinner", "off"],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []  # pip-audit failed (e.g. no internet); skip dependency checks
    lines = req.read_text(encoding="utf-8").splitlines()
    findings = []
    for dep in data.get("dependencies", []):
        vulns = dep.get("vulns") or []
        if not vulns:
            continue
        name = dep["name"]
        line_no = next((i for i, l in enumerate(lines, 1) if l.strip().lower().startswith(name.lower())), 1)
        fixes = [v for vuln in vulns for v in vuln.get("fix_versions", [])]
        fix = str(max(Version(v) for v in fixes)) if fixes else None
        findings.append(Finding(
            file="requirements.txt", line_start=line_no, line_end=line_no,
            vuln_class="vulnerable_dependency", severity="high",
            source_tool="pip-audit", rule_id=f"DEP:{name.lower()}",
            message=f"{name} {dep['version']} has known vulnerabilities: "
                    + ", ".join(v["id"] for v in vulns)
                    + (f". Fixed in {fix}." if fix else ". No fixed version yet."),
            code_snippet=lines[line_no - 1].strip() if lines else "",
        ))
    return findings
