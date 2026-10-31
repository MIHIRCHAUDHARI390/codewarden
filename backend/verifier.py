import shutil
import tempfile
from collections import Counter
from pathlib import Path

from sandbox import pytest_in_sandbox
from scanner import scan
from schemas import Finding, Patch, VerificationResult

MAX_CHANGED_LINES = 40
OK = {"pass", "fail_as_expected", "not_applicable", "no_baseline_tests"}
SKIP_DIRS = shutil.ignore_patterns(".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache")


def verify(finding: Finding, patch: Patch, project_root: str, original: str) -> VerificationResult:
    checks: dict[str, str] = {}
    logs: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="codewarden-"))
    try:
        orig_dir, patched_dir = tmp / "original", tmp / "patched"
        for d, content in ((orig_dir, original), (patched_dir, patch.patched_content)):
            shutil.copytree(project_root, d, ignore=SKIP_DIRS)
            write(d / finding.file, content)
            if patch.regression_test:
                write(d / patch.regression_test.path, patch.regression_test.content)

        # 1. Patch applies cleanly to original file (no conflicts), and patch changes something.
        on_disk = (Path(project_root) / finding.file).read_text(encoding="utf-8")
        if on_disk != original:
            checks["patch_applies"] = "file_changed_since_scan"
        elif not patch.unified_diff:
            checks["patch_applies"] = "empty_diff"
        else:
            checks["patch_applies"] = "pass"

        # 2. Syntax check (compile only parses, does not run code).
        checks["syntax_ok"] = "pass"
        to_compile = [(finding.file, patch.patched_content)]
        if patch.regression_test:
            to_compile.append((patch.regression_test.path, patch.regression_test.content))
        for path, src in to_compile:
            if path.endswith(".py"):
                try:
                    compile(src, path, "exec")
                except SyntaxError as e:
                    checks["syntax_ok"] = "fail"
                    logs.append(f"[syntax] {path}: {e}")

        # 3. Small diff that only touches the vulnerable file (plus new test file).
        changed = sum(1 for l in patch.unified_diff.splitlines()
                      if l[:1] in "+-" and not l.startswith(("+++", "---")))
        checks["diff_in_scope"] = "pass" if changed <= MAX_CHANGED_LINES else f"too_large ({changed} lines)"

        # Don't spend time in Docker if the basics already failed.
        if any(checks[k] != "pass" for k in checks):
            return result(finding, patch, checks, logs)

        # 4. Regression test: must fail on original and pass on patched (run inside Docker).
        if patch.regression_test:
            test = patch.regression_test.path
            code, out = pytest_in_sandbox(orig_dir, test)
            logs.append(f"[regression test on original]\n{out}")
            checks["regression_test_before"] = "fail_as_expected" if code == 1 else "did_not_fail" if code == 0 else f"error (exit {code})"
            code, out = pytest_in_sandbox(patched_dir, test)
            logs.append(f"[regression test on patched]\n{out}")
            checks["regression_test_after"] = "pass" if code == 0 else "still_fails"
        else:
            checks["regression_test_before"] = checks["regression_test_after"] = "not_applicable"

        # 5. Existing tests must still pass on the patched code.
        if (patched_dir / "tests").is_dir() or (patched_dir / "pytest.ini").exists():
            args = [f"--ignore={patch.regression_test.path}"] if patch.regression_test else []
            code, out = pytest_in_sandbox(patched_dir, *args)
            logs.append(f"[existing tests on patched]\n{out}")
            checks["existing_tests"] = "pass" if code == 0 else "no_baseline_tests" if code == 5 else "fail"
        else:
            checks["existing_tests"] = "no_baseline_tests"

        # 6. Re-scan: the original finding is gone and nothing new appeared.
        before = Counter((f.vuln_class, f.rule_id) for f in scan(orig_dir, [finding.file]))
        after = Counter((f.vuln_class, f.rule_id) for f in scan(patched_dir, [finding.file]))
        key = (finding.vuln_class, finding.rule_id)
        checks["rescan_clean"] = "pass" if after[key] < before[key] else "still_reported"
        new = after - before
        checks["no_new_findings"] = "pass" if not new else "new: " + ", ".join(f"{c}/{r}" for c, r in new)

        return result(finding, patch, checks, logs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def result(finding, patch, checks, logs) -> VerificationResult:
    return VerificationResult(
        finding_id=finding.id,
        attempt=patch.attempt,
        verified=all(v in OK for v in checks.values()),
        checks=checks,
        logs="\n".join(logs)[-6000:],  # keep the end, where pytest prints failures
    )


def feedback(v: VerificationResult, patch: Patch) -> dict:
    """What went wrong, in a form the Patch agent can act on."""
    return {
        "failed_checks": {k: r for k, r in v.checks.items() if r not in OK},
        "your_previous_diff": patch.unified_diff,
        "log_tail": v.logs[-2500:],
    }


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")