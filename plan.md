# CodeWarden - Build Plan (From Scratch)

**Goal:** Build an agentic AI security guard for Python code that demonstrates multi-agent orchestration, deterministic verification, sandbox isolation, and Human-in-the-Loop (HITL) patch approval. Optimized for a professor demo -> maximum grade.

**Current State (as of rebuild):**
- `backend/` - **emptied**, ready for from-scratch implementation
- `extension/` - original VS Code extension intact (reference only)
- `demo_apps/vulnapp/` - original seeded vulnerable app intact (reference only)
- `codewarden_reference/` - full backup of original working code (use for reference, not copy-paste)
- `agentic_security_guard.md` - updated spec (LangGraph, subprocess Docker CLI, Mistral, sync /patch)
- `.gitignore`, `README.md` - intact

---

## Core Architecture Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestrator | **LangGraph** | Multi-agent state machine with conditional edges, checkpoints, and visual graph export |
| LLM Provider | **Mistral API via httpx** | Structured JSON output, no vendor lock-in |
| Scanner Tools | **Bandit + regex secrets + AST path traversal + pip-audit** | Semgrep/gitleaks are stretch goals |
| Sandbox | **subprocess + Docker CLI** | Transparent commands, easier to inspect and debug |
| Patch Endpoint | **Synchronous /patch** | Job polling/SSE is a stretch goal |
| HITL UI | **Inline Accept/Decline** | Diff editor + Quick Fix approval flow |
| Verifier | **Pure Python, 7 deterministic checks** | No LLM judgment - key safety differentiator |

---

## Phase-by-Phase Build Order

Write files in this exact order. Each phase produces something testable.

### Phase 1: Data Contracts & Host Setup (Foundational)
**Files:** `backend/schemas.py`, `backend/requirements.txt`, `backend/pytest.ini`
- **Host Dependencies:** Ensure `bandit==1.8.3` and `pip-audit==2.9.0` are installed alongside `fastapi`, `uvicorn`, `pydantic`, `langgraph`, `pytest`, `httpx`.
- **Pydantic Models (`schemas.py`):**
  - `Finding`: file, line range, vuln_class, severity, source_tool, rule_id, message, code_snippet, status, triage_rationale
  - `RegressionTest`: path, content
  - `Explanation`: what_was_wrong, why_it_matters, what_changed
  - `Patch`: finding_id, attempt, unified_diff, patched_content, regression_test, explanation
  - `VerificationResult`: finding_id, attempt, verified, checks dictionary, logs
  - `Evidence`: finding_id, explanation details, checks_passed, verification metadata
  - API Request/Response models: `ScanRequest`, `ScanResponse`, `PatchRequest`, `PatchResponse`, `DecisionRequest`
- **Test:** Import all models, instantiate a `Finding`, serialize to JSON and validate aliases (`class` -> `vuln_class`).

### Phase 2: Scanner Agent (Detection)
**File:** `backend/scanner.py`
- `run_bandit(root, files)`: Run Bandit JSON output -> `Finding` objects mapped via `BANDIT_MAP`.
- `find_secrets(file, text)`: Regex patterns for API keys, tokens, passwords with line numbers.
- `find_path_traversal(file, text)`: AST visitor flagging `open()` calls with dynamically constructed paths lacking path containment guards.
- `run_pip_audit(root)`: `pip-audit` JSON parser flagging known CVEs in `requirements.txt` and extracting fix versions.
- `scan(root, files)`: Top-level entry orchestrating all scanners, returns raw list of findings.
- **Test:** Run scanner against `demo_apps/vulnapp/`, assert all 5 code vulnerability classes + vulnerable dependency are accurately detected.

### Phase 3: Triage Agent (Filtering)
**File:** `backend/triage.py`
- `triage(findings)`:
  - Deduplicate findings reported across multiple tools by `(file, line_start, vuln_class)`.
  - Severity mapping: `command_injection` = critical, `sql_injection` = high, `unsafe_deserialization` = high, `path_traversal` = high, `hardcoded_secret` = medium, `vulnerable_dependency` = medium.
  - Automatically classify findings in `tests/` or files starting with `test_` as `status="dismissed"` ("Finding is in test code, not shipped code.").
  - Rank confirmed findings by severity, file path, and line number.
- **Test:** Deduplicate identical findings reported by multiple tools; confirm test-code findings are marked dismissed while application code is marked confirmed.

### Phase 4: Sandbox & Deterministic Verifier Gate
**Files:** `backend/Dockerfile.sandbox`, `backend/sandbox.py`, `backend/verifier.py`
- **Sandbox Container (`Dockerfile.sandbox`):**
  - Base `python:3.12.7-slim`, pre-install `pytest==8.3.3` and `pyyaml==6.0.2`.
  - Non-root user `sandbox` (UID 1000), default working directory `/work`.
  - Tag as `codewarden-sandbox`.
- **Sandbox Runner (`sandbox.py`):**
  - `run_in_sandbox(workdir, command)` using `subprocess.run(["docker", "run", ...])`.
  - Enforcement flags: `--network none`, `--read-only`, `--tmpfs /tmp`, `--user 1000:1000`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--cpus 1`, `--memory 512m`, `--pids-limit 128`, 60-second timeout.
  - `pytest_in_sandbox(workdir, *args)` helper.
- **Deterministic Verifier (`verifier.py`):**
  - Evaluates the 7 safety gates:
    1. `patch_applies`: Target file unchanged since scan; non-empty diff.
    2. `syntax_ok`: `compile()` passes without SyntaxError for both patched file and regression test.
    3. `diff_in_scope`: Changed lines <= 40 lines.
    4. `regression_test_before`: Exploit test exits with code 1 on unpatched code (`fail_as_expected`).
    5. `regression_test_after`: Exploit test exits with code 0 on patched code (`pass`).
    6. `existing_tests`: Original test suite passes on patched code.
    7. `rescan_clean` & `no_new_findings`: Original scanner finding disappears; no new findings created.
  - `feedback(verification, patch)`: Formats structured retry feedback (failed checks, diff, pytest failure log tail).
- **Test:** Verify valid SQLi patch passes all checks; verify broken patch (failing baseline tests or invalid syntax) is rejected with structured reasons.

### Phase 5: Patch Agent (LLM Fix Generation & Redaction)
**File:** `backend/patcher.py`
- `redact(text)` / `unredact(text, secrets)`: Automatically replace secret tokens with `<REDACTED_N>` before sending code to LLM, restoring them after patch generation.
- `bump_dependency(finding, original, attempt)`: Deterministic version bump in `requirements.txt` for dependencies without calling LLM.
- `generate_patch(finding, original, attempt, feedback, model, project_root)`:
  - Formulates prompt with vulnerability details, class-specific hints (`FIX_HINTS`), project tests, and prior verifier feedback on retries.
  - Calls Mistral API (`mistral-large-4` or user-specified model) using `httpx` with strict JSON schema.
  - Generates unified diff locally via `difflib.unified_diff` (never trusts raw LLM diffs).
- **Test:** SQLi patch generation returns valid JSON diff and regression test; secret redaction protects test tokens; dependency bump updates `pyyaml==5.4`.

### Phase 6: Orchestrator (LangGraph State Machine)
**File:** `backend/pipeline.py`
- **State Schema:**
  ```python
  class PatchState(TypedDict):
      finding: Finding
      project_root: str
      original_content: str
      attempt: int
      max_attempts: int
      model: str | None
      current_patch: Patch | None
      verification: VerificationResult | None
      feedback: dict | None
      status: Literal["patching", "verifying", "verified", "failed", "escalated"]
      message: str
  ```
- **Graph Nodes:**
  - `generate_patch_node`: Generates candidate patch and regression test (using verifier feedback if attempt > 1).
  - `verify_patch_node`: Executes the 7 verifier checks in the Docker sandbox, logs attempt to database.
  - `escalate_node`: Builds final unverified response after retries exhausted.
- **Conditional Routing:**
  - If `verification.verified == True` -> route to `END`.
  - If `verification.checks["patch_applies"] == "file_changed_since_scan"` -> route to `escalate_node` -> `END`.
  - If `verification.verified == False` and `attempt < max_attempts` -> increment attempt, set feedback, route back to `generate_patch_node`.
  - If `verification.verified == False` and `attempt >= max_attempts` -> route to `escalate_node` -> `END`.
- **Graph Visualization:** Provide `get_pipeline_graph_ascii()` / `get_pipeline_graph_mermaid()` so the compiled state graph can be printed in logs or rendered for the presentation.
- **Test:** Unit test state transitions: first attempt fails verification -> triggers retry with feedback -> second attempt passes.

### Phase 7: Backend API & Storage
**Files:** `backend/main.py`, `backend/db.py`
- **Database (`db.py`):** SQLite schema with `runs`, `findings`, `attempts`, and `decisions` tables.
- **FastAPI Endpoints (`main.py`):**
  - `GET /health`: Checks Docker availability, sandbox image existence, and LLM key status.
  - `POST /scan`: Receives file contents, writes temp project context, runs `scan()` + `triage()`, saves run to SQLite, returns findings.
  - `POST /patch`: Invokes the LangGraph orchestrator pipeline, returns `PatchResponse` with verified patch, explanation, and evidence summary.
  - `POST /decision`: Logs user's `accepted` or `declined` decision with optional reason.
  - `GET /runs/{run_id}`: Retrieves run history and finding status.
- **Test:** Test client invoking `/health`, `/scan`, `/patch`, and `/decision` endpoints.

### Phase 8: Evaluation Harness & Ablations (Grade Maximizer)
**Files:** `backend/evaluate.py`, `evaluation/results.md`
- Runs automated evaluation against `demo_apps/vulnapp/` comparing **4 Ablation Baselines**:
  1. **Baseline 1 (Scanner Only):** Detection rate & raw false-positive rate.
  2. **Baseline 2 (LLM Patch No Verification):** LLM patch applied blindly without sandbox testing (measure test breakage / regression rate).
  3. **Baseline 3 (Full System Without Triage):** Measures noise reduction and unnecessary patch attempts on test files.
  4. **Baseline 4 (Full CodeWarden System):** Complete multi-agent pipeline with Docker sandbox verification and self-correction retries.
- **Metrics Collected:**
  - Detection recall on seeded vulnerabilities (6/6 classes)
  - False-positive reduction percentage post-triage
  - Patch verification success rate
  - Average retries to fix
  - Regression rate (should be 0% on verified patches)
  - Execution time per finding
- **Output:** Formats automated comparison table into `evaluation/results.md`.

### Phase 9: VS Code Extension Integration
**Files:** `extension/src/extension.ts`, `extension/package.json`
- **Build Extension:**
  ```powershell
  cd extension
  npm.cmd install
  npm.cmd run compile
  ```
- **Features Tested:**
  - `securityGuard.scanWorkspace`: Editor squiggles & Problems panel integration with severity levels.
  - Quick Fix Lightbulb: "Generate verified patch" triggers progress notification.
  - Diff View: Opens `vscode.diff` between disk file and virtual document `codewarden-patched://`.
  - Evidence Report: Summarizes vulnerability cause, why it matters, what changed, and sandbox checks passed.
  - HITL Actions: Accept replaces code and writes regression test file; Decline captures feedback to backend.
- **Test:** Launch Extension Development Host (F5) against `demo_apps/vulnapp/`, scan, generate patch, view diff, and accept.

---

## What to Show the Professor (Demo Script)

1. **System Health & Graph:** Show `GET /health` and display the compiled LangGraph state diagram.
2. **Scan in VS Code:** Open `demo_apps/vulnapp/app/db.py`, trigger scan -> highlight SQL injection error squiggle.
3. **Trigger Verified Patch:** Click lightbulb Quick Fix -> watch backend output logs showing Docker sandbox executing pytest without network.
4. **Self-Correction (if retry triggered):** Show how verifier failure log was fed back into Mistral prompt to generate the working fix.
5. **Diff & Evidence Review:** Review side-by-side diff in VS Code diff editor alongside evidence summary.
6. **Accept Action:** Click "Accept" -> observe file update and automatic creation of `tests/test_sec_f_*.py`.
7. **Present Evaluation Table:** Show `evaluation/results.md` highlighting 0% regression rate and the 4 ablation baselines.

---

## Key Talking Points for Maximum Grade

- **Not just an LLM wrapper:** Four distinct agents (Scanner, Triage, Patch, Verifier) orchestrated via a formal LangGraph state machine.
- **Deterministic verification gate:** The verifier is pure code (pytest, compile checks, rescan)—never trusts an LLM to self-certify its own code.
- **Autonomous self-correction:** Verifier returns machine-readable failure logs -> Patch agent adapts and retries (up to 3 attempts).
- **True sandbox isolation:** Ephemeral Docker containers, network disabled (`--network none`), read-only root, non-root user (UID 1000), dropped privileges.
- **Strict Human-in-the-Loop (HITL):** Code only modifies after human review; user decisions are audited in SQLite.
- **Scientific evaluation:** Defended by 4 ablation studies and quantitative security metrics.

---

## Reference Locations

- Original working code (reference only): `codewarden_reference/`
- Updated spec: `agentic_security_guard.md`
- This plan: `plan.md`

---

## Files NOT to Touch During Build

- `agentic_security_guard.md` - spec is locked
- `codewarden_reference/` - backup reference, do not modify
- `.gitignore` - already configured
- `README.md` - update only after build is complete