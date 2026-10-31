"""Phase 2 tests: verify scanner detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner import scan

DEMO = Path(__file__).resolve().parents[2] / "demo_apps" / "vulnapp"


def test_scanner_finds_all_code_classes():
    files = [p.relative_to(DEMO).as_posix() for p in DEMO.rglob("*.py")]
    classes = {f.vuln_class for f in scan(DEMO, files)}
    assert classes >= {"sql_injection", "command_injection", "path_traversal",
                       "unsafe_deserialization", "hardcoded_secret"}


def test_scanner_finds_vulnerable_dependency():
    files = ["requirements.txt"]
    findings = scan(DEMO, files)
    assert any(f.vuln_class == "vulnerable_dependency" for f in findings)