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

export function activate(context: vscode.ExtensionContext) {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  setStatus("idle");
  statusBar.show();

  context.subscriptions.push(
    diagnostics, output, statusBar,
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
    vscode.window.showInformationMessage(`Security Guard: ${res.findings.length} finding(s).`);
  } catch (e) {
    setStatus("error");
    vscode.window.showErrorMessage(`Security Guard scan failed: ${e}`);
    return;
  }
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
    vscode.window.showWarningMessage("No security finding on this line. Run 'Security Guard: Scan File' first.");
    return;
  }
  const finding = findings.get(diag.code as string);
  if (!finding) {
    vscode.window.showWarningMessage("Security finding not in memory. Run 'Security Guard: Scan Workspace' to refresh.");
    return;
  }

  const fileUri = editor.document.uri;
  const folder = vscode.workspace.getWorkspaceFolder(fileUri)!;
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
  vscode.window.showInformationMessage("Patch applied.");
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
