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
const findings = new Map<string, Finding>();          // finding id -> finding
const scannedText = new Map<string, string>();        // file uri -> text that was scanned
const patchedDocs = new Map<string, string>();        // virtual uri -> patched content
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
    for (const f of res.findings as Finding[]) {
      if (SEVERITY_RANK[f.severity] < threshold) continue;
      findings.set(f.id, f);
      const diag = new vscode.Diagnostic(
        new vscode.Range(f.line_start - 1, 0, f.line_end - 1, Number.MAX_SAFE_INTEGER),
        `[${f.severity}] ${f.class.replace(/_/g, " ")}: ${f.message}`,
        f.severity === "critical" || f.severity === "high" ? vscode.DiagnosticSeverity.Error
          : f.severity === "medium" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information,
      );
      diag.source = "Security Guard";
      diag.code = f.id;
      byFile.set(f.file, [...(byFile.get(f.file) ?? []), diag]);
    }
    for (const [file, diags] of byFile) {
      diagnostics.set(vscode.Uri.joinPath(folder.uri, file), diags);
    }
    setStatus(res.findings.length ? `${res.findings.length} issue(s)` : "clean");
  } catch (e) {
    setStatus("error");
    vscode.window.showErrorMessage(`Security Guard scan failed: ${e}`);
  }
}

// ---------------- Quick fix -> patch -> diff -> accept/decline ----------------

function provideCodeActions(doc: vscode.TextDocument, _range: vscode.Range, ctx: vscode.CodeActionContext) {
  return ctx.diagnostics
    .filter((d) => d.source === "Security Guard")
    .map((d) => {
      const action = new vscode.CodeAction("Generate verified patch", vscode.CodeActionKind.QuickFix);
      action.command = { command: "securityGuard.generatePatch", title: "Generate verified patch", arguments: [d.code, doc.uri] };
      action.diagnostics = [d];
      return action;
    });
}

async function generatePatch(findingId?: string, fileUri?: vscode.Uri) {
  if (!findingId || !fileUri) {
    vscode.window.showInformationMessage("Use the lightbulb (Quick Fix) on a Security Guard warning.");
    return;
  }
  const finding = findings.get(findingId);
  if (!finding) return;

  setStatus("patching");
  let res: PatchResponse;
  try {
    res = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Security Guard: generating patch and verifying it in the sandbox…" },
      () => post("/patch", {
        run_id: finding.run_id,
        finding_id: finding.id,
        max_retries: config().get("maxRetries"),
        model: config().get<string>("model") || null,
      }),
    );
  } catch (e) {
    setStatus("error");
    vscode.window.showErrorMessage(`Security Guard patch failed: ${e}`);
    return;
  }
  setStatus("idle");

  if (!res.verified || !res.patch || !res.evidence) {
    vscode.window.showWarningMessage(`No verified fix: ${res.message}`);
    return;
  }

  // Show original vs patched in VS Code's diff editor.
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

function setStatus(text: string) {
  statusBar.text = `$(shield) Security Guard: ${text}`;
}
