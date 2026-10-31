# 📦 How to Install CodeWarden Extension in VS Code

This guide covers **two methods**: the easy way (VSIX install) and the manual way (development mode).

---

## Prerequisites

Before installing the extension, make sure the **backend is running**:

```cmd
cd C:\Users\sange\codewarden\backend
set MISTRAL_API_KEY=your-api-key-here
.venv\Scripts\activate
uvicorn main:app --port 8765
```

Verify: open http://127.0.0.1:8765/health in your browser. You should see `{"backend":"ok",...}`.

---

## Method 1: Easy Install (VSIX) — Recommended

### Step 1: Build the VSIX package

```cmd
cd C:\Users\sange\codewarden\extension
npm install
npm run compile
vsce package --no-dependencies
```

This creates `codewarden-0.1.0.vsix` in the extension folder.

### Step 2: Install in VS Code

**Option A — Command line:**
```cmd
code --install-extension C:\Users\sange\codewarden\extension\codewarden-0.1.0.vsix
```

**Option B — VS Code UI:**
1. Open VS Code
2. Press `Ctrl+Shift+P` → type "Extensions: Install from VSIX..."
3. Select `C:\Users\sange\codewarden\extension\codewarden-0.1.0.vsix`
4. Click "Install"
5. Reload VS Code when prompted

### Step 3: Use it

1. Open any Python project folder in VS Code
2. Press `Ctrl+Shift+P` → "Security Guard: Scan Workspace"
3. Squiggly lines appear on vulnerable code
4. Click the lightbulb 💡 → "Generate verified patch"
5. Review the diff → Accept or Decline

### To uninstall
```cmd
code --uninstall-extension codewarden.codewarden
```

### To update after code changes
```cmd
cd C:\Users\sange\codewarden\extension
npm run compile
vsce package --no-dependencies
code --install-extension codewarden-0.1.0.vsix --force
```

---

## Method 2: Manual Install (Development Mode)

Use this if you want to edit the extension source code and see changes immediately.

### Step 1: Open the extension folder in VS Code

```cmd
code C:\Users\sange\codewarden\extension
```

### Step 2: Install dependencies and compile

```cmd
npm install
npm run compile
```

### Step 3: Launch the Extension Development Host

1. Press `F5` (or Run → Start Debugging)
2. A new VS Code window opens (Extension Development Host)
3. The extension is now active in that window

### Step 4: Open a Python project in the new window

1. In the new VS Code window, open `C:\Users\sange\codewarden\demo_apps\vulnapp`
2. Press `Ctrl+Shift+P` → "Security Guard: Scan Workspace"
3. Squiggly lines appear on vulnerable code

### Step 5: Make changes and reload

- Edit `extension/src/extension.ts`
- Press `Ctrl+Shift+F5` to reload the Extension Development Host
- Or use `npm run watch` for auto-recompile on save

### Troubleshooting F5

If F5 fails with "preLaunchTask 'npm: compile' terminated":
- Make sure `extension/.vscode/tasks.json` exists (see below)
- Run `npm run compile` manually first
- Then press F5 again

---

## Method 3: Symlink (Advanced)

For development without packaging, symlink the extension folder to VS Code's extensions directory:

```cmd
mklink /D "%USERPROFILE%\.vscode\extensions\codewarden" "C:\Users\sange\codewarden\extension"
```

Then reload VS Code. The extension loads from the symlinked folder.

To remove:
```cmd
rmdir "%USERPROFILE%\.vscode\extensions\codewarden"
```

---

## Quick Reference

| Task | Command |
|---|---|
| Build VSIX | `cd extension && vsce package --no-dependencies` |
| Install VSIX | `code --install-extension extension/codewarden-0.1.0.vsix` |
| Uninstall | `code --uninstall-extension codewarden.codewarden` |
| Compile (dev) | `cd extension && npm run compile` |
| Launch (dev) | Open extension/ in VS Code → press F5 |
| Watch mode (dev) | `cd extension && npm run watch` |

---

## Troubleshooting

### Extension not showing in VS Code
- Make sure `extension/out/extension.js` exists (run `npm run compile`)
- Check VS Code version: `code --version` (need 1.90+)
- Try reloading: `Ctrl+Shift+P` → "Developer: Reload Window"

### "Security Guard" commands not appearing
- The extension activates on Python files or `requirements.txt`
- Open a `.py` file or a folder containing `requirements.txt`
- Check Output panel: View → Output → "Security Guard"

### Backend connection failed
- Ensure backend is running: `curl http://127.0.0.1:8765/health`
- Check `securityGuard.backendUrl` setting in VS Code

### PowerShell execution policy error
If `npm` commands fail in PowerShell:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Or use `cmd` instead of PowerShell.

---

**Built for:** VS Code 1.90+, Python 3.11+, Node.js 18+, Docker Desktop