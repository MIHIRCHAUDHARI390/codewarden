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
let findingsTreeProvider: FindingsTreeProvider;
let statusTreeProvider: StatusTreeProvider;

// ---------------- Tree View Providers ----------------

class FindingTreeItem extends vscode.TreeItem {
  constructor(public readonly finding: Finding) {
    const fileName = finding.file.split("/").pop() || finding.file;
    super(`${fileName}:${finding.line_start} - ${finding.class.replace(/_/g, " ")}`, vscode.TreeItemCollapsibleState.None);
    
    this.description = `[${finding.severity.toUpperCase()}]`;
    this.tooltip = new vscode.MarkdownString(
      `### ${finding.message}\n\n` +
      `- **File:** \`${finding.file}:${finding.line_start}\`\n` +
      `- **Class:** \`${finding.class}\`\n` +
      `- **Severity:** \`${finding.severity.toUpperCase()}\`\n` +
      `- **Rationale:** ${finding.triage_rationale || "Confirmed vulnerability"}\n\n` +
      `*Click to navigate. Click 🛠️ to generate verified patch.*`
    );
    this.contextValue = "findingItem";

    if (finding.severity === "critical" || finding.severity === "high") {
      this.iconPath = new vscode.ThemeIcon("error", new vscode.ThemeColor("errorForeground"));
    } else if (finding.severity === "medium") {
      this.iconPath = new vscode.ThemeIcon("warning", new vscode.ThemeColor("problemsWarningIcon.foreground"));
    } else {
      this.iconPath = new vscode.ThemeIcon("info", new vscode.ThemeColor("problemsInfoIcon.foreground"));
    }

    this.command = {
      command: "securityGuard.openFinding",
      title: "Open Finding",
      arguments: [finding],
    };
  }
}

class FindingsTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private currentFindings: Finding[] = [];

  refresh(newFindings?: Finding[]) {
    if (newFindings) {
      this.currentFindings = newFindings;
    } else {
      this.currentFindings = Array.from(findings.values());
    }
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (element) return [];
    if (this.currentFindings.length === 0) {
      const item = new vscode.TreeItem("No security findings");
      item.description = "Workspace clean or not scanned yet";
      item.iconPath = new vscode.ThemeIcon("shield");
      return [item];
    }
    return this.currentFindings.map((f) => new FindingTreeItem(f));
  }
}

class StatusTreeItem extends vscode.TreeItem {
  constructor(label: string, description: string, icon: string, color?: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = description;
    this.iconPath = color ? new vscode.ThemeIcon(icon, new vscode.ThemeColor(color)) : new vscode.ThemeIcon(icon);
  }
}

class StatusTreeProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private healthData: { backend?: string; sandbox_image_ready?: boolean; llm_configured?: boolean } | null = null;
  private isChecking = false;

  refresh() {
    this.checkHealth();
  }

  async checkHealth() {
    if (this.isChecking) return;
    this.isChecking = true;
    try {
      const url = config().get<string>("backendUrl") + "/health";
      const r = await fetch(url);
      if (r.ok) {
        this.healthData = (await r.json()) as any;
      } else {
        this.healthData = null;
      }
    } catch {
      this.healthData = null;
    } finally {
      this.isChecking = false;
      this._onDidChangeTreeData.fire();
    }
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (element) return [];
    const items: vscode.TreeItem[] = [];

    if (this.healthData) {
      items.push(new StatusTreeItem("Backend Server", "Online (port 8765)", "pass-filled", "testing.iconPassed"));
      items.push(
        this.healthData.sandbox_image_ready
          ? new StatusTreeItem("Docker Sandbox", "Ready (codewarden-sandbox)", "package", "testing.iconPassed")
          : new StatusTreeItem("Docker Sandbox", "Image missing", "error", "errorForeground")
      );
      items.push(
        this.healthData.llm_configured
          ? new StatusTreeItem("Mistral AI", `Active (${config().get<string>("model") || "codestral-latest"})`, "sparkle", "testing.iconPassed")
          : new StatusTreeItem("Mistral AI", "Key missing (vulnerable_dependency only)", "warning", "problemsWarningIcon.foreground")
      );
    } else {
      items.push(new StatusTreeItem("Backend Server", "Offline (Check localhost:8765)", "error", "errorForeground"));
      items.push(new StatusTreeItem("Docker Sandbox", "Unavailable", "circle-slash"));
      items.push(new StatusTreeItem("Mistral AI", "Unavailable", "circle-slash"));
    }

    const findingCount = findings.size;
    items.push(new StatusTreeItem("Active Findings", `${findingCount} detected`, findingCount > 0 ? "shield" : "pass", findingCount > 0 ? "problemsWarningIcon.foreground" : "testing.iconPassed"));

    return items;
  }
}

// ---------------- Extension Activation ----------------

export function activate(context: vscode.ExtensionContext) {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  setStatus("idle");
  statusBar.show();

  findingsTreeProvider = new FindingsTreeProvider();
  statusTreeProvider = new StatusTreeProvider();

  context.subscriptions.push(
    diagnostics, output, statusBar,
    vscode.window.registerTreeDataProvider("codewarden.findingsView", findingsTreeProvider),
    vscode.window.registerTreeDataProvider("codewarden.statusView", statusTreeProvider),
    vscode.commands.registerCommand("securityGuard.scanFile", scanActiveFile),
    vscode.commands.registerCommand("securityGuard.scanWorkspace", scanWorkspace),
    vscode.commands.registerCommand("securityGuard.generatePatch", generatePatch),
    vscode.commands.registerCommand("securityGuard.patchFromTree", patchFromTree),
    vscode.commands.registerCommand("securityGuard.openFinding", openFinding),
    vscode.commands.registerCommand("securityGuard.refreshStatus", () => statusTreeProvider.refresh()),
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

  // Initial status check
  statusTreeProvider.refresh();
}

export function deactivate() {}

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

    // Refresh tree views
    findingsTreeProvider.refresh(Array.from(findings.values()));
    statusTreeProvider.refresh();

    vscode.window.showInformationMessage(`Security Guard: ${res.findings.length} finding(s) detected.`);
  } catch (e) {
    setStatus("error");
    vscode.window.showErrorMessage(`Security Guard scan failed: ${e}`);
    return;
  }
  setStatus("idle");
}

// ---------------- Navigation & Actions ----------------

async function openFinding(finding: Finding) {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return;
  const uri = vscode.Uri.joinPath(folder.uri, finding.file);
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc);
    const line = Math.max(0, finding.line_start - 1);
    const range = new vscode.Range(line, 0, line, 100);
    editor.selection = new vscode.Selection(range.start, range.end);
    editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  } catch (err) {
    vscode.window.showErrorMessage(`Unable to open file ${finding.file}: ${err}`);
  }
}

async function patchFromTree(item?: FindingTreeItem) {
  if (item && item.finding) {
    await runPatchForFinding(item.finding);
  }
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
  const apiKey = config().get<string>("apiKey") || undefined;

  setStatus("patching");
  let res: PatchResponse;
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
    vscode.window.showErrorMessage(`Security Guard patch failed: ${e}`);
    return;
  }
  setStatus("idle");

  if (!res.verified || !res.patch || !res.evidence) {
    if (res.message && res.message.includes("MISTRAL_API_KEY")) {
      vscode.window.showErrorMessage(
        "Mistral API key is required to generate AI fixes. Set 'securityGuard.apiKey' in VS Code settings or set MISTRAL_API_KEY on the backend."
      );
    } else {
      vscode.window.showWarningMessage(`No verified fix: ${res.message || "Checks failed in sandbox."}`);
    }
    return;
  }

  const patchedUri = vscode.Uri.from({ scheme: PATCHED_SCHEME, path: fileUri.path, query: finding.id });
  patchedDocs.set(patchedUri.toString(), res.patch.patched_content);
  await vscode.commands.executeCommand("vscode.diff", fileUri, patchedUri, `Security fix: ${finding.class.replace(/_/g, " ")}`);

  const ev = res.evidence;
  output.clear();
  output.appendLine(`Finding ${finding.id}  (${finding.class}, ${finding.severity})`);
  output.appendLine(`\nWhat was wrong:  ${ev.what_was_wrong}`);
  output.appendLine(`Why it matters:  ${ev.why_it_matters}`);
  output.appendLine(`What changed:    ${ev.what_changed}`);
  output.appendLine(`\nChecks:\n  ${ev.checks_passed.join("\n  ")}`);
  if (res.patch.regression_test) output.appendLine(`\nRegression test added: ${res.patch.regression_test.path}`);
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

  // Remove finding from list and refresh views
  findings.delete(finding.id);
  findingsTreeProvider.refresh(Array.from(findings.values()));
  statusTreeProvider.refresh();

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
