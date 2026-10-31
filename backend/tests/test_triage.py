"""Phase 3 tests: verify triage logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import Finding
from triage import triage


def test_triage_dedupes_and_dismisses_test_code():
    def make(file, tool):
        return Finding(file=file, line_start=3, line_end=3, vuln_class="sql_injection",
                       severity="low", source_tool=tool, rule_id="B608", message="m")

    out = triage([make("app/a.py", "bandit"), make("app/a.py", "semgrep"),
                  make("tests/test_a.py", "bandit")])
    assert len(out) == 2
    assert out[0].status == "confirmed" and out[0].severity == "high"
    assert out[1].status == "dismissed"
    assert out[1].triage_rationale == "Finding is in test code, not shipped code."