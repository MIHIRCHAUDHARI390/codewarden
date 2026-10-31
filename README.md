# Codewarden
Agentic VS Code extension that scans Python code for security flaws, tests fixes in a Docker sandbox, and proposes verified patches for your approval.

Full spec: [agentic_security_guard.md](agentic_security_guard.md)

## Layout

```
backend/            Python + FastAPI (one file per component)
  main.py           API: /scan /patch /decision /runs/{id} /health
  schemas.py        data contracts (spec section 11)
  scanner.py        Scanner agent: Bandit, secret regex, path-traversal rule, pip-audit
  triage.py         Triage agent: dedupe, severity, drop false positives
  patcher.py        Patch agent: Mistral writes the fix + a regression test
  sandbox.py        runs tests in Docker (no network, non-root, read-only, limits)
  verifier.py       deterministic pass/fail checks (spec section 8)
  pipeline.py       patch -> verify -> retry with feedback (max 3)
  db.py             SQLite log
  Dockerfile.sandbox
extension/src/extension.ts   VS Code extension
demo_apps/vulnapp/           seeded vulnerable app (one bug per class) with tests
```

## Run it

Needs Python 3.11+, Node 18+, Docker Desktop running, and a Mistral API key.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
docker build -t codewarden-sandbox -f Dockerfile.sandbox .
set MISTRAL_API_KEY=...           # PowerShell: $env:MISTRAL_API_KEY="..."
uvicorn main:app --port 8765

# 2. Tests (no API key needed; the LLM is faked)
python -m pytest -q

# 3. Extension
cd ../extension
npm install
npm run compile
# Open the extension/ folder in VS Code and press F5.
# A new window opens on demo_apps/vulnapp. Save a file or run "Security Guard: Scan Workspace",
# then use the lightbulb on a warning -> "Generate verified patch".
```

## How a patch gets verified

A patch is shown to you only if all of these pass:
the file did not change since the scan, the code compiles, the diff is at most 40 lines,
the regression test fails on the old code and passes on the new code (inside Docker),
existing tests still pass (inside Docker), the re-scan no longer reports the issue, and no new issues appear.
