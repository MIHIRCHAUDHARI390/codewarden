# CodeWarden - Your AI Security Guard for Python

> 🚀 **Quick Start Guide:** [START.md - शुरू करने की 1-Click पूरी गाइड](./START.md)
>
> Nothing reaches you unless it passed objective checks. Nothing changes your code unless you approve it.

CodeWarden is a VS Code extension that automatically scans your Python code for security vulnerabilities, generates fixes using AI, tests those fixes in an isolated Docker sandbox, and shows you a verified patch. You decide: Accept or Decline.

No auto-commits. No breaking your code. No trusting an AI blindly.
## What It Detects

| Vulnerability | Example | Severity |
|---|---|---|
| Hardcoded Secrets | API_KEY = sk-abc123 | Medium |
| SQL Injection | query = SELECT * FROM users WHERE name = %s | High |
| Command Injection | subprocess.check_output with shell=True | Critical |
| Path Traversal | open(os.path.join(NOTES_DIR, name)) | High |
| Unsafe Deserialization | yaml.load(text, Loader=yaml.Loader) | High |
| Vulnerable Dependencies | pyyaml 5.3.1 (known CVE) | Medium |

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop
- Mistral API Key (free tier works)

## Installation

### 1. Clone the repository

git clone https://github.com/nikunjkumar05/codewarden.git
cd codewarden

### 2. Set up the backend

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

### 3. Build the Docker sandbox image

docker build -t codewarden-sandbox -f Dockerfile.sandbox .

### 4. Set your Mistral API key

set MISTRAL_API_KEY=your-api-key-here

### 5. Start the backend

uvicorn main:app --port 8765

### 6. Install the VS Code extension

cd ../extension
npm install
npm run compile
code --install-extension codewarden-0.1.0.vsix

## How to Use

1. Open a Python project in VS Code
2. Press Ctrl+Shift+P and run Security Guard: Scan Workspace
3. Squiggly lines appear under vulnerable code
4. Click the lightbulb on a finding and select Generate verified patch
5. Review the diff view and evidence summary
6. Click Accept to apply the fix or Decline to discard

## How It Works

CodeWarden uses 4 AI agents working together:

1. Scanner - finds vulnerabilities using Bandit, regex, AST, pip-audit
2. Triage - deduplicates, ranks by severity, filters false positives
3. Patch - LLM generates a fix and regression test
4. Verifier - runs 7 deterministic checks in a Docker sandbox

A patch is shown to you only if ALL 7 checks pass. If any fail, the verifier sends feedback to the Patch agent and retries (up to 3 times).

## Configuration

Open VS Code Settings and search for Security Guard:

- backendUrl: Backend server URL (default: http://127.0.0.1:8765)
- scanOnSave: Auto-scan on file save (default: true)
- model: Mistral model ID (empty = default)
- maxRetries: Max patch retry attempts (default: 3)
- severityThreshold: Minimum severity to show (default: low)

## Troubleshooting

- Scan failed: Make sure the backend is running on port 8765
- No verified fix: The AI could not generate a passing fix. Try increasing maxRetries
- Docker not ready: Ensure Docker Desktop is running and the image is built
- API key not set: Run set MISTRAL_API_KEY=your-key before starting the backend

## FAQ

Q: Does this send my code to the cloud?
A: Code is sent to the Mistral API for patch generation only. Secrets are redacted first. The backend runs locally.

Q: Will it break my existing code?
A: No. Every patch is verified against your existing test suite. If tests break, the patch is rejected.

Q: Does it work offline?
A: Scanning works offline. Patch generation requires the Mistral API.

## Project Structure

backend/ - Python + FastAPI backend
  main.py - API endpoints
  schemas.py - Data contracts
  scanner.py - Vulnerability detection
  triage.py - Finding filtering and ranking
  patcher.py - LLM fix generation
  sandbox.py - Docker sandbox runner
  verifier.py - 7 deterministic checks
  pipeline.py - Orchestrator with retry loop
  db.py - SQLite logging
  Dockerfile.sandbox - Sandbox Docker image
  evaluate.py - Evaluation harness
  tests/ - Backend tests
extension/ - VS Code extension (TypeScript)
demo_apps/vulnapp/ - Seeded vulnerable app
agentic_security_guard.md - Full project specification
plan.md - Build plan and phases

## License

MIT

Built with Python, FastAPI, LangGraph, Mistral AI, Docker, TypeScript, VS Code Extension API
