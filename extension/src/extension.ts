import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

// ---- Types matching backend/schemas.py ----
interface Finding {
  id: string; run_id: string; file: string; line_start: number; line_end: number;
  class: string; severity: string; message: string; triage_rationale: string;
}
interface PatchResponse {
  verified: boolean;
  message: string;
  patch?: { patched_content: string; regression_test?: { path: string; content: string } };
  evidence?: { what_was_wrong: string; why_it_matters: string; what_changed: string; checks_passed: string[] };
}

const SEVERITY_RANK: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
const PATCHED_SCHEME = "codewarden-patched";

const diagnostics = vscode.languages.createDiagnosticCollection("securityGuard");
const output = vscode.window.createOutputChannel("Security Guard");
const findings = new Map<string, Finding>();
const scannedText = new Map<string, string>();
const patchedDocs = new Map<string, string>();
let statusBar: vscode.StatusBarItem;
let dashboardProvider: CodeWardenDashboardProvider;

// ---------------- Webview Dashboard Provider ----------------

class CodeWardenDashboardProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "codewarden.dashboard";
  private _view?: vscode.WebviewView;

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    this._view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getHtml();

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.command) {
        case "scanWorkspace":
          await scanWorkspace();
          break;
        case "scanFile":
          await scanActiveFile();
          break;
        case "openFinding":
          await openFindingById(msg.findingId);
          break;
        case "generatePatch":
          const f = findings.get(msg.findingId);
          if (f) await runPatchForFinding(f);
          break;
        case "saveApiKey":
          await saveApiKey(msg.apiKey);
          break;
        case "startBackend":
          await startBackend();
          break;
        case "refreshHealth":
          await this.syncHealth();
          break;
        case "ready":
          await this.syncHealth();
          this.syncFindings();
          this.syncApiKey();
          break;
      }
    });

    this.syncHealth();
    this.syncFindings();
    this.syncApiKey();
  }

  setStatus(status: "idle" | "scanning" | "patching", message: string) {
    if (this._view) {
      this._view.webview.postMessage({ type: "status", status, message });
    }
  }

  syncFindings() {
    if (this._view) {
      this._view.webview.postMessage({
        type: "findings",
        findings: Array.from(findings.values()),
      });
    }
  }

  syncApiKey() {
    const key = config().get<string>("apiKey") || "";
    if (this._view) {
      this._view.webview.postMessage({ type: "apiKey", apiKey: key });
    }
  }

  async syncHealth() {
    try {
      const url = config().get<string>("backendUrl") + "/health";
      const r = await fetch(url);
      if (r.ok) {
        const data = (await r.json()) as any;
        if (this._view) {
          this._view.webview.postMessage({
            type: "health",
            online: true,
            sandbox: !!data.sandbox_image_ready,
            llm: !!data.llm_configured,
            model: config().get<string>("model") || "codestral-latest",
          });
        }
        return;
      }
    } catch {}
    if (this._view) {
      this._view.webview.postMessage({
        type: "health",
        online: false,
        sandbox: false,
        llm: false,
        model: config().get<string>("model") || "codestral-latest",
      });
    }
  }

  private getHtml(): string {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CodeWarden</title>
  <style>
    :root {
      --bg: var(--vscode-sideBar-background);
      --card-bg: var(--vscode-editor-background);
      --text: var(--vscode-foreground);
      --muted: var(--vscode-descriptionForeground);
      --border: var(--vscode-widget-border, rgba(128,128,128,0.35));
      --hover: color-mix(in srgb, var(--text) 6%, transparent);
      --accent: var(--vscode-button-background);
      --accent-hover: var(--vscode-button-hoverBackground);
      --btn-fg: var(--vscode-button-foreground);
      --success: var(--vscode-testing-iconPassed, #89d185);
      --warning: var(--vscode-charts-yellow, #d7ba7d);
      --danger: var(--vscode-errorForeground, #f14c4c);
      --info: var(--vscode-textLink-foreground, #3794ff);
      --font: var(--vscode-font-family, -apple-system, sans-serif);
      --mono: var(--vscode-editor-font-family, monospace);
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 13px;
      line-height: 1.45;
    }
    body { padding: 12px; }

    /* ---------- Header ---------- */
    .masthead {
      display: flex; align-items: center; gap: 8px;
      padding-bottom: 10px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }
    .masthead svg { width: 18px; height: 18px; flex-shrink: 0; }
    .shield { fill: var(--info); }
    .mark { font-size: 13px; font-weight: 600; letter-spacing: 0.2px; }
    .mark em {
      font-style: normal; color: var(--muted); font-weight: 500;
      margin-left: 6px; font-size: 12px;
    }

    /* ---------- Status ---------- */
    .status-row {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--card-bg);
      margin-bottom: 12px;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
    .status-card.idle .dot { background: var(--success); }
    .status-card.scanning .dot { background: var(--info); animation: blink 1s infinite; }
    .status-card.patching .dot { background: var(--warning); animation: blink 0.8s infinite; }
    @keyframes blink { 50% { opacity: 0.3; } }
    .status-info { flex: 1; min-width: 0; }
    .status-title { font-size: 12px; font-weight: 600; color: var(--text); }
    .status-desc {
      font-size: 11px; color: var(--muted);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    /* remove dependency on pulsing dot layout used by JS className switching */
    .status-card .dot { display: block; }

    /* ---------- Offline card ---------- */
    .offline-card {
      border: 1px solid var(--warning);
      border-radius: 4px;
      background: color-mix(in srgb, var(--warning) 8%, transparent);
      padding: 10px 12px;
      margin-bottom: 12px;
    }
    .offline-title { font-weight: 600; font-size: 12px; color: var(--warning); }
    .offline-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

    /* ---------- Controls ---------- */
    .section-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px;
      color: var(--muted); font-weight: 600; margin: 12px 0 6px;
    }
    .key-row { display: flex; gap: 6px; }
    .key-input {
      flex: 1; min-width: 0;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border, var(--border));
      border-radius: 3px;
      padding: 5px 8px;
      font-size: 12px;
      font-family: var(--mono);
      outline: none;
    }
    .key-input:focus { border-color: var(--accent); }

    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      background: var(--accent);
      color: var(--btn-fg);
      border: 1px solid transparent;
      border-radius: 3px;
      padding: 6px 10px;
      font-size: 12px; font-weight: 500;
      cursor: pointer;
      font-family: inherit;
    }
    .btn:hover { background: var(--accent-hover); }
    .btn-secondary { background: transparent; border-color: var(--border); color: var(--text); }
    .btn-secondary:hover { background: var(--hover); }
    .btn-sm { padding: 4px 9px; font-size: 11px; }
    .btn-block { width: 100%; }
    .btn-start { margin-bottom: 0; }

    /* ---------- Health ---------- */
    .health-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }
    .pill {
      font-size: 11px; padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid var(--border);
      color: var(--muted);
      white-space: nowrap;
    }
    .pill.active { color: var(--success); border-color: var(--success); }
    .pill[style*="cursor"] { cursor: pointer; }

    /* ---------- Findings ---------- */
    .findings-head {
      display: flex; justify-content: space-between; align-items: center;
      margin: 16px 0 8px;
    }
    .findings-head .count { font-size: 11px; color: var(--muted); }
    .finding-card {
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--card-bg);
      padding: 10px 12px;
      margin-bottom: 8px;
    }
    .finding-card.high, .finding-card.critical { border-left: 3px solid var(--danger); }
    .finding-card.medium { border-left: 3px solid var(--warning); }
    .finding-card.low { border-left: 3px solid var(--info); }
    .card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .sev-tag {
      font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px;
      padding: 1px 7px; border-radius: 9px;
      border: 1px solid var(--border); color: var(--muted);
    }
    .sev-tag.sev-high, .sev-tag.sev-critical { color: var(--danger); border-color: var(--danger); }
    .sev-tag.sev-medium { color: var(--warning); border-color: var(--warning); }
    .sev-tag.sev-low { color: var(--info); border-color: var(--info); }
    .file-loc { font-size: 11px; color: var(--muted); font-family: var(--mono); }
    .vuln-title { font-weight: 600; font-size: 12px; margin: 7px 0 2px; text-transform: capitalize; }
    .vuln-msg { font-size: 11px; color: var(--muted); margin-bottom: 8px; }
    .card-actions { display: flex; gap: 6px; }
    .card-actions .btn { flex: 1; }

    .empty-state {
      text-align: center; color: var(--muted);
      padding: 28px 12px;
      border: 1px dashed var(--border); border-radius: 4px;
    }
    .empty-state .big { font-size: 15px; margin-bottom: 4px; }
    .empty-state .hint { font-size: 11px; margin-top: 2px; }
  </style>
</head>
<body>

  <div class="masthead">
    <svg class="shield" viewBox="0 0 24 24">
      <path d="M12 2 3.5 5.8v5.7c0 5.3 3.7 9.9 8.5 11.3 4.8-1.4 8.5-6 8.5-11.3V5.8L12 2Z"/>
      <circle cx="12" cy="11.5" r="2" fill="var(--bg)"/>
    </svg>
    <div class="mark">CodeWarden<em>Security Guard</em></div>
  </div>

  <!-- Live Status -->
  <div id="statusCard" class="status-card idle status-row">
    <div class="dot"></div>
    <div class="status-info">
      <div id="statusTitle" class="status-title">System Ready</div>
      <div id="statusDesc" class="status-desc">Scan a workspace to check for vulnerabilities</div>
    </div>
  </div>

  <!-- Offline startup -->
  <div id="backendOfflineCard" class="offline-card" style="display:none">
    <div class="offline-title">Backend is offline</div>
    <div class="offline-sub">The local server must be running for scans &amp; AI fixes.</div>
    <div style="margin-top:8px">
      <button id="startBackendBtn" class="btn btn-start">Start backend server</button>
    </div>
  </div>

  <!-- API key -->
  <div class="section-label">Mistral API key</div>
  <div class="key-row">
    <input type="password" id="apiKeyInput" class="key-input" placeholder="mstrl_...">
    <button id="saveKeyBtn" class="btn btn-sm">Save</button>
  </div>
  <div style="margin-top:4px">
    <span id="keyBadge" class="pill">Missing</span>
  </div>

  <!-- Actions -->
  <div class="section-label">Actions</div>
  <button id="scanWsBtn" class="btn btn-block">Scan entire workspace</button>
  <div style="height:6px"></div>
  <button id="scanFileBtn" class="btn btn-secondary btn-block">Scan active file</button>

  <!-- Health -->
  <div class="section-label">Environment</div>
  <div class="health-row">
    <span id="pillBackend" class="pill" title="Click to start backend" style="cursor:pointer">Backend: Checking…</span>
    <span id="pillDocker" class="pill">Sandbox: Checking…</span>
    <span id="pillModel" class="pill">codestral-latest</span>
    <span id="restartBtn" class="pill" title="Restart backend" style="cursor:pointer">Restart</span>
  </div>

  <!-- Findings -->
  <div class="findings-head">
    <span class="section-label" style="margin:0">Security findings</span>
    <span id="findingsCount" class="count">0 detected</span>
  </div>
  <div id="findingsList">
    <div class="empty-state">
      <div class="big">No scan yet</div>
      <div>Scanned issues will appear here</div>
      <div class="hint">Press “Scan entire workspace” to begin</div>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    const statusCard = document.getElementById('statusCard');
    const statusTitle = document.getElementById('statusTitle');
    const statusDesc = document.getElementById('statusDesc');
    const backendOfflineCard = document.getElementById('backendOfflineCard');
    const startBackendBtn = document.getElementById('startBackendBtn');
    const restartBtn = document.getElementById('restartBtn');
    const keyBadge = document.getElementById('keyBadge');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const saveKeyBtn = document.getElementById('saveKeyBtn');
    const scanWsBtn = document.getElementById('scanWsBtn');
    const scanFileBtn = document.getElementById('scanFileBtn');
    const pillBackend = document.getElementById('pillBackend');
    const pillDocker = document.getElementById('pillDocker');
    const pillModel = document.getElementById('pillModel');
    const findingsList = document.getElementById('findingsList');
    const findingsCount = document.getElementById('findingsCount');

    // Button Listeners
    startBackendBtn?.addEventListener('click', () => {
      vscode.postMessage({ command: 'startBackend' });
    });
    restartBtn?.addEventListener('click', () => {
      vscode.postMessage({ command: 'startBackend' });
    });
    pillBackend?.addEventListener('click', () => {
      vscode.postMessage({ command: 'startBackend' });
    });
    scanWsBtn.addEventListener('click', () => {
      vscode.postMessage({ command: 'scanWorkspace' });
    });
    scanFileBtn.addEventListener('click', () => {
      vscode.postMessage({ command: 'scanFile' });
    });
    saveKeyBtn.addEventListener('click', () => {
      const key = apiKeyInput.value.trim();
      if (key) {
        vscode.postMessage({ command: 'saveApiKey', apiKey: key });
      }
    });

    // Handle messages from Extension
    window.addEventListener('message', (event) => {
      const msg = event.data;
      switch (msg.type) {
        case 'status':
          updateStatus(msg.status, msg.message);
          break;
        case 'health':
          updateHealth(msg);
          break;
        case 'apiKey':
          updateApiKey(msg.apiKey);
          break;
        case 'findings':
          renderFindings(msg.findings);
          break;
      }
    });

    function updateStatus(status, message) {
      statusCard.className = 'status-card ' + status + ' status-row';
      if (status === 'scanning') {
        statusTitle.textContent = 'Scanning workspace…';
        statusDesc.textContent = message || 'Running Bandit, AST, secrets &amp; pip-audit…';
        scanWsBtn.disabled = true;
      } else if (status === 'patching') {
        statusTitle.textContent = 'Generating patch…';
        statusDesc.textContent = message || 'AI fix generation &amp; sandbox verification…';
        scanWsBtn.disabled = true;
      } else {
        statusTitle.textContent = 'System Ready';
        statusDesc.textContent = message || 'Workspace scan complete or idle';
        scanWsBtn.disabled = false;
      }
    }

    function updateHealth(h) {
      if (h.online) {
        if (backendOfflineCard) backendOfflineCard.style.display = 'none';
        pillBackend.textContent = 'Backend: Online';
        pillBackend.className = 'pill active';
      } else {
        if (backendOfflineCard) backendOfflineCard.style.display = 'block';
        pillBackend.textContent = 'Backend: Offline (click to start)';
        pillBackend.className = 'pill';
      }

      if (h.sandbox) {
        pillDocker.textContent = 'Sandbox: Ready';
        pillDocker.className = 'pill active';
      } else {
        pillDocker.textContent = 'Sandbox: Missing';
        pillDocker.className = 'pill';
      }

      pillModel.textContent = h.model || 'codestral-latest';
    }

    function updateApiKey(key) {
      if (key) {
        keyBadge.textContent = 'Configured';
        keyBadge.className = 'pill active';
        apiKeyInput.value = key;
      } else {
        keyBadge.textContent = 'Missing';
        keyBadge.className = 'pill';
      }
    }

    function renderFindings(items) {
      findingsCount.textContent = items.length + ' detected';
      if (!items || items.length === 0) {
        findingsList.innerHTML = \`
          <div class="empty-state">
            <div class="big">No vulnerabilities found</div>
            <div>Workspace code is clean</div>
          </div>\`;
        return;
      }

      findingsList.innerHTML = items.map(f => {
        const sevClass = 'sev-' + (f.severity || 'low');
        const cardClass = 'finding-card ' + (f.severity || 'low');
        const fileName = f.file.split('/').pop() || f.file;
        const prettyClass = (f.class || '').replace(/_/g, ' ');

        return \`
          <div class="\${cardClass}">
            <div class="card-top">
              <span class="sev-tag \${sevClass}">\${f.severity || 'INFO'}</span>
              <span class="file-loc">\${fileName}:\${f.line_start}</span>
            </div>
            <div class="vuln-title">\${prettyClass}</div>
            <div class="vuln-msg">\${f.message}</div>
            <div class="card-actions">
              <button class="btn btn-secondary" onclick="openItem('\${f.id}')">View</button>
              <button class="btn" onclick="patchItem('\${f.id}')">Fix with AI</button>
            </div>
          </div>\`;
      }).join('');
    }

    window.openItem = function(id) {
      vscode.postMessage({ command: 'openFinding', findingId: id });
    };
    window.patchItem = function(id) {
      vscode.postMessage({ command: 'generatePatch', findingId: id });
    };

    // Notify ready
    vscode.postMessage({ command: 'ready' });
  </script>
</body>
</html>

`;
  }
}

// ---------------- Extension Activation ----------------

export function activate(context: vscode.ExtensionContext) {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  statusBar.command = "securityGuard.openDashboard";
  statusBar.tooltip = "CodeWarden: Click to open Security Guard dashboard";
  setStatus("idle");
  statusBar.show();

  dashboardProvider = new CodeWardenDashboardProvider(context.extensionUri);

  context.subscriptions.push(
    diagnostics, output, statusBar,
    vscode.window.registerWebviewViewProvider(CodeWardenDashboardProvider.viewType, dashboardProvider),
    vscode.commands.registerCommand("securityGuard.openDashboard", async () => {
      await vscode.commands.executeCommand("workbench.view.extension.codewarden-sidebar");
    }),
    vscode.commands.registerCommand("securityGuard.startBackend", startBackend),
    vscode.commands.registerCommand("securityGuard.scanFile", scanActiveFile),
    vscode.commands.registerCommand("securityGuard.scanWorkspace", scanWorkspace),
    vscode.commands.registerCommand("securityGuard.generatePatch", generatePatch),
    vscode.workspace.registerTextDocumentContentProvider(PATCHED_SCHEME, {
      provideTextDocumentContent: (uri) => patchedDocs.get(uri.toString()) ?? "",
    }),
    vscode.languages.registerCodeActionsProvider({ scheme: "file" }, { provideCodeActions }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (config().get("scanOnSave") && isScannable(doc.uri)) {
        scanDocuments([doc]);
      }
    }),
  );
}

export function deactivate() {}

// ---------------- Backend Launcher ----------------

function findProjectRoot(): string {
  const folders = vscode.workspace.workspaceFolders || [];
  for (const f of folders) {
    let current = f.uri.fsPath;
    for (let i = 0; i < 6; i++) {
      if (
        fs.existsSync(path.join(current, "start.bat")) ||
        fs.existsSync(path.join(current, "backend", "main.py"))
      ) {
        return current;
      }
      const parent = path.dirname(current);
      if (!parent || parent === current) break;
      current = parent;
    }
  }

  const activeFile = vscode.window.activeTextEditor?.document.uri.fsPath;
  if (activeFile) {
    let current = path.dirname(activeFile);
    for (let i = 0; i < 6; i++) {
      if (
        fs.existsSync(path.join(current, "start.bat")) ||
        fs.existsSync(path.join(current, "backend", "main.py"))
      ) {
        return current;
      }
      const parent = path.dirname(current);
      if (!parent || parent === current) break;
      current = parent;
    }
  }

  return folders[0]?.uri.fsPath || "C:\\Users\\rahul\\codewarden";
}

async function startBackend() {
  // Check if backend is already healthy
  try {
    const url = (config().get<string>("backendUrl") || "http://127.0.0.1:8765") + "/health";
    const res = await fetch(url);
    if (res.ok) {
      vscode.window.showInformationMessage("CodeWarden: Backend server is already running and online!");
      await dashboardProvider.syncHealth();
      return;
    }
  } catch {}

  let terminal = vscode.window.terminals.find((t) => t.name === "CodeWarden Backend");
  if (!terminal) {
    terminal = vscode.window.createTerminal("CodeWarden Backend");
  }
  terminal.show(false);

  dashboardProvider.setStatus("scanning", "Starting backend server...");

  const root = findProjectRoot();
  const startBat = path.join(root, "start.bat");
  const backendDir = path.join(root, "backend");

  if (process.platform === "win32") {
    terminal.sendText(`cd "${root}"; if (Test-Path "${startBat}") { & "${startBat}" } else { cd "${backendDir}"; .\\.venv\\Scripts\\uvicorn.exe main:app --host 127.0.0.1 --port 8765 --reload }`);
  } else {
    const startSh = path.join(root, "start.sh");
    terminal.sendText(`cd "${root}"; if [ -f "${startSh}" ]; then "${startSh}"; else cd "${backendDir}" && ./.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765 --reload; fi`);
  }

  vscode.window.showInformationMessage("CodeWarden: Starting backend server in terminal...");

  for (const delay of [2500, 5000, 8000, 12000]) {
    setTimeout(async () => {
      await dashboardProvider.syncHealth();
    }, delay);
  }
}

// ---------------- API Key Management ----------------

async function saveApiKey(newKey: string) {
  try {
    const cleanKey = newKey.trim().replace(/^["']|["']$/g, "");
    await config().update("apiKey", cleanKey, vscode.ConfigurationTarget.Global);
    dashboardProvider.syncApiKey();
    await dashboardProvider.syncHealth();
    vscode.window.showInformationMessage("Mistral API key saved successfully!");
  } catch (e) {
    vscode.window.showErrorMessage(`Failed to save API key: ${e}`);
  }
}

// ---------------- Navigation ----------------

async function openFindingById(findingId: string) {
  const f = findings.get(findingId);
  if (!f) return;
  const root = findProjectRoot();
  let fileFsPath = path.isAbsolute(f.file) ? f.file : path.join(root, f.file);
  if (!fs.existsSync(fileFsPath)) {
    const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (ws && fs.existsSync(path.join(ws, f.file))) {
      fileFsPath = path.join(ws, f.file);
    }
  }
  const uri = vscode.Uri.file(fileFsPath);
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc);
    const line = Math.max(0, f.line_start - 1);
    const range = new vscode.Range(line, 0, line, 100);
    editor.selection = new vscode.Selection(range.start, range.end);
    editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  } catch (err) {
    vscode.window.showErrorMessage(`Unable to open file ${f.file}: ${err}`);
  }
}

// ---------------- Scanning ----------------

async function scanActiveFile() {
  const doc = vscode.window.activeTextEditor?.document;
  if (!doc || !isScannable(doc.uri)) {
    vscode.window.showWarningMessage("Open a Python file or requirements.txt to scan.");
    return;
  }
  await scanDocuments([doc]);
}

async function scanWorkspace() {
  const uris = await vscode.workspace.findFiles("{**/*.py,requirements.txt}", "{**/.venv/**,**/venv/**,**/node_modules/**}");
  const docs = await Promise.all(uris.map((u) => vscode.workspace.openTextDocument(u)));
  await scanDocuments(docs);
}

async function scanDocuments(docs: vscode.TextDocument[]) {
  const folder = docs.length ? vscode.workspace.getWorkspaceFolder(docs[0].uri) : undefined;
  if (!folder) {
    vscode.window.showWarningMessage("Security Guard needs the file to be inside an open folder.");
    return;
  }
  const files = docs.map((d) => ({ path: relPath(folder, d.uri), content: d.getText() }));

  setStatus("scanning");
  dashboardProvider.setStatus("scanning", `Scanning ${files.length} project file(s)...`);

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "CodeWarden",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: `Scanning workspace for vulnerabilities...` });
      try {
        const res = await post("/scan", { project_root: folder.uri.fsPath, files });
        const threshold = SEVERITY_RANK[config().get<string>("severityThreshold") ?? "low"];

        for (const d of docs) {
          diagnostics.delete(d.uri);
          scannedText.set(d.uri.toString(), d.getText());
        }
        const byFile = new Map<string, vscode.Diagnostic[]>();
        findings.clear();

        for (const f of res.findings) {
          if (SEVERITY_RANK[f.severity] < threshold) continue;
          const uri = vscode.Uri.joinPath(folder.uri, f.file);
          const lineStart = Math.max(0, f.line_start - 1);
          const lineEnd = Math.max(lineStart, f.line_end - 1);
          const range = new vscode.Range(lineStart, 0, lineEnd, 1000);
          const diag = new vscode.Diagnostic(range, `${f.message} (${f.class})`, toSeverity(f.severity));
          diag.source = "Security Guard";
          diag.code = f.id;
          byFile.set(uri.toString(), [...(byFile.get(uri.toString()) ?? []), diag]);
          findings.set(f.id, f);
        }
        for (const [uriStr, diags] of byFile) {
          diagnostics.set(vscode.Uri.parse(uriStr), diags);
        }

        // Sync to webview
        dashboardProvider.syncFindings();
        dashboardProvider.setStatus("idle", `Scan complete: ${res.findings.length} finding(s) found`);
        vscode.window.showInformationMessage(`Security Guard: ${res.findings.length} finding(s) detected.`);
      } catch (e) {
        setStatus("error");
        dashboardProvider.setStatus("idle", `Scan failed: ${e}`);
        vscode.window.showErrorMessage(`Security Guard scan failed: ${e}`);
      }
    }
  );

  setStatus("idle");
}

// ---------------- Patching ----------------

async function generatePatch(actionDiag?: vscode.Diagnostic) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  const fileDiags = diagnostics.get(editor.document.uri) ?? [];
  const curPos = editor.selection.start;
  const diag = (actionDiag && typeof actionDiag.code === "string") ? actionDiag : (
    fileDiags.find((d) => d.range.contains(curPos) || (curPos.line >= d.range.start.line && curPos.line <= d.range.end.line))
    ?? fileDiags[0]
  );

  if (!diag || typeof diag.code !== "string") {
    vscode.window.showWarningMessage("No security finding on this line. Run 'Security Guard: Scan Workspace' first.");
    return;
  }
  const finding = findings.get(diag.code as string);
  if (!finding) {
    vscode.window.showWarningMessage("Security finding not in memory. Run 'Security Guard: Scan Workspace' to refresh.");
    return;
  }

  await runPatchForFinding(finding);
}

async function runPatchForFinding(finding: Finding) {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return;
  const fileUri = vscode.Uri.joinPath(folder.uri, finding.file);

  const maxRetries = config().get<number>("maxRetries") ?? 3;
  const model = config().get<string>("model") || undefined;
  const rawKey = config().get<string>("apiKey") || "";
  const apiKey = rawKey.trim().replace(/^["']|["']$/g, "") || undefined;

  setStatus("patching");
  dashboardProvider.setStatus("patching", `Patching ${finding.class.replace(/_/g, " ")} & verifying in Docker...`);

  let res: PatchResponse | undefined;

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "CodeWarden",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: `Generating fix with AI & testing 7 checks in Docker sandbox...` });
      try {
        res = await post("/patch", {
          run_id: finding.run_id,
          finding_id: finding.id,
          max_retries: maxRetries,
          model,
          api_key: apiKey,
        });
      } catch (e) {
        setStatus("error");
        dashboardProvider.setStatus("idle", `Patch failed: ${e}`);
        vscode.window.showErrorMessage(`Security Guard patch failed: ${e}`);
        return;
      }
    }
  );

  setStatus("idle");
  dashboardProvider.setStatus("idle", "Patch attempt finished");

  if (!res || !res.verified || !res.patch || !res.evidence) {
    const msg = res?.message || "Checks failed in sandbox.";
    if (msg.includes("MISTRAL_API_KEY") || msg.includes("Invalid API Key")) {
      vscode.window.showErrorMessage(
        "Mistral API key is invalid or not configured. Please enter your valid key in the CodeWarden sidebar."
      );
    } else {
      vscode.window.showWarningMessage(`No verified fix: ${msg}`);
    }
    return;
  }

  const patchedUri = vscode.Uri.from({ scheme: PATCHED_SCHEME, path: fileUri.path, query: finding.id });
  patchedDocs.set(patchedUri.toString(), res.patch.patched_content);
  await vscode.commands.executeCommand("vscode.diff", fileUri, patchedUri, `Security fix: ${finding.class.replace(/_/g, " ")}`);

  const ev = res.evidence;
  output.clear();
  const rule = "=".repeat(56);
  output.appendLine(rule);
  output.appendLine(`  VERIFIED SECURITY FIX  ·  ${finding.id}`);
  output.appendLine(rule);
  output.appendLine(`Vulnerability : ${finding.class.replace(/_/g, " ")}  (${finding.severity})`);
  output.appendLine(`File          : ${finding.file}:${finding.line_start}`);
  output.appendLine("");
  output.appendLine("What was wrong");
  output.appendLine("───────────────");
  output.appendLine(`  ${ev.what_was_wrong}`);
  output.appendLine("");
  output.appendLine("Why it matters");
  output.appendLine("───────────────");
  output.appendLine(`  ${ev.why_it_matters}`);
  output.appendLine("");
  output.appendLine("What changed");
  output.appendLine("────────────");
  output.appendLine(`  ${ev.what_changed}`);
  output.appendLine("");
  output.appendLine("Verification checks");
  output.appendLine("───────────────────");
  ev.checks_passed.forEach((c) => output.appendLine(`  ✓ ${c}`));
  if (res.patch.regression_test) output.appendLine("");
  if (res.patch.regression_test) output.appendLine(`Regression test added: ${res.patch.regression_test.path}`);
  output.appendLine(rule);
  output.show(true);

  const choice = await vscode.window.showInformationMessage(
    `Verified patch ready: ${ev.what_changed}`, "Accept", "Decline",
  );
  if (choice === "Accept") {
    await accept(finding, fileUri, res);
  } else if (choice === "Decline") {
    const reason = await vscode.window.showInputBox({ prompt: "Why decline? (optional)" });
    await post("/decision", { finding_id: finding.id, decision: "declined", reason: reason || null });
  }
  patchedDocs.delete(patchedUri.toString());
}

async function accept(finding: Finding, fileUri: vscode.Uri, res: PatchResponse) {
  const doc = await vscode.workspace.openTextDocument(fileUri);
  if (doc.getText() !== scannedText.get(fileUri.toString())) {
    vscode.window.showWarningMessage("The file changed since the scan, so the patch was not applied. Scan again.");
    return;
  }
  const edit = new vscode.WorkspaceEdit();
  edit.replace(fileUri, new vscode.Range(0, 0, doc.lineCount, 0), res.patch!.patched_content);
  const test = res.patch!.regression_test;
  const folder = vscode.workspace.getWorkspaceFolder(fileUri)!;
  if (test) {
    const testUri = vscode.Uri.joinPath(folder.uri, test.path);
    edit.createFile(testUri, { overwrite: true, contents: new TextEncoder().encode(test.content) });
  }
  await vscode.workspace.applyEdit(edit);
  await doc.save();
  await post("/decision", { finding_id: finding.id, decision: "accepted", reason: null });

  // Remove from list and update UI
  findings.delete(finding.id);
  dashboardProvider.syncFindings();

  vscode.window.showInformationMessage("Patch applied successfully.");
}

// ---------------- Code Actions ----------------

function provideCodeActions(document: vscode.TextDocument, range: vscode.Range): vscode.CodeAction[] {
  const fileDiags = diagnostics.get(document.uri) ?? [];
  const lineRange = new vscode.Range(range.start.line, 0, range.end.line, 1000);
  const matched = fileDiags.filter((d) => 
    d.range.intersection(lineRange) || 
    d.range.contains(range.start) ||
    (range.start.line >= d.range.start.line && range.start.line <= d.range.end.line)
  );
  const targetDiags = matched.length ? matched : (fileDiags.length === 1 ? fileDiags : []);
  return targetDiags.map((d) => {
    const action = new vscode.CodeAction("Generate verified patch", vscode.CodeActionKind.QuickFix);
    action.command = { command: "securityGuard.generatePatch", title: "Generate verified patch", arguments: [d] };
    action.diagnostics = [d];
    action.isPreferred = true;
    return action;
  });
}

// ---------------- Helpers ----------------

async function post(path: string, body: unknown): Promise<any> {
  const url = config().get<string>("backendUrl") + path;
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

function config() {
  return vscode.workspace.getConfiguration("securityGuard");
}

function isScannable(uri: vscode.Uri) {
  return uri.scheme === "file" && (uri.path.endsWith(".py") || uri.path.endsWith("/requirements.txt"));
}

function relPath(folder: vscode.WorkspaceFolder, uri: vscode.Uri) {
  return path.relative(folder.uri.fsPath, uri.fsPath).replace(/\\/g, "/");
}

function toSeverity(s: string): vscode.DiagnosticSeverity {
  return s === "critical" ? vscode.DiagnosticSeverity.Error
    : s === "high" ? vscode.DiagnosticSeverity.Error
    : s === "medium" ? vscode.DiagnosticSeverity.Warning
    : vscode.DiagnosticSeverity.Information;
}

function setStatus(text: string) {
  statusBar.text = `$(shield) Security Guard: ${text}`;
}
