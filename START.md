# 🛡️ CodeWarden Security Guard — Complete Startup Guide (शुरू करने की पूरी गाइड)

Swagat hai! Yeh guide aapko **CodeWarden** ko **1-Click** me start karne aur use karne ke sabhi tareeqe step-by-step samjhati hai.

---

## ⚡ Quick Navigation (जल्दी शुरू करें)

1. [🚀 1-Click Startup (सबसे आसान तरीका)](#-1-1-click-startup-सबसे-आसान-तरीका)
2. [📍 VS Code Sidebar me Extension Kahan Dikhayi Dega?](#-2-vs-code-sidebar-me-extension-kahan-dikhayi-dega)
3. [🔑 Mistral AI API Key Setup](#-3-mistral-ai-api-key-setup)
4. [🛡️ Code Scan Kaise Karein](#-4-code-scan-kaise-karein)
5. [⚡ AI Patch & Sandbox Verification Kaise Use Karein](#-5-ai-patch--sandbox-verification-kaise-use-karein)
6. [🧪 Seeded Vulnerable Demo App se Test Karein](#-6-seeded-vulnerable-demo-app-se-test-karein)
7. [🛠️ Troubleshooting & FAQs](#-7-troubleshooting--faqs)

---

## 🚀 1. 1-Click Startup (सबसे आसान तरीका)

CodeWarden ko start karne ke **2 simple 1-click tareeqe** hain:

### Tareeqa A: VS Code Sidebar Dashboard se (Recommended)
1. VS Code ke left Activity Bar me **CodeWarden Shield (🛡️)** icon par click karein.
2. Agar backend offline hai, toh aapko green button dikhega:
   ```
   [ 🚀 1-Click Start Backend Server ]
   ```
3. Bas us button par click karein! CodeWarden automatically terminal open karega aur sabhi services start kar dega.

### Tareeqa B: Desktop / Explorer se `start.bat` chalao
1. Project root folder (`codewarden/`) me jayein.
2. **`start.bat`** file par double-click karein!
3. Yeh script automatically:
   - ✅ **Docker Desktop** running hai ya nahi check karega (aur start karega agar band ho).
   - ✅ **Docker Sandbox Image** (`codewarden-sandbox`) verify/build karega.
   - ✅ Python virtual environment (`.venv`) aur dependencies verify karega.
   - ✅ FastAPI Backend server ko port `8765` par start kar dega!

> 💡 **PowerShell Users:** Aap terminal me `.\start.ps1` bhi run kar sakte hain.

Backend start hone ke baad:
- **Backend URL:** `http://127.0.0.1:8765`
- **Swagger Docs:** `http://127.0.0.1:8765/docs`
- **Health Check:** `http://127.0.0.1:8765/health`

---

## 📍 2. VS Code Sidebar me Extension Kahan Dikhayi Dega?

Agar VS Code ke left side bar (Activity Bar) me CodeWarden ka icon nahi dikh raha hai, toh yeh simple steps follow karein:

### Step 1: VS Code Window Reload Karein (Zaroori)
Extension install hone ke baad VS Code ko ek baar reload karna hota hai:
- Keyboard par **`Ctrl + Shift + P`** dabayein.
- Type karein: `Developer: Reload Window` aur **Enter** dabayein.

### Step 2: Activity Bar par Right-Click Karein
Agar aapke VS Code me bohot saare extensions installed hain (jaise Python, C++, Thunder Client, Wokwi, etc.), toh icons overflow ho sakte hain:
1. Left side ke kisi bhi icon par **Right-Click** karein.
2. Ek context menu open hoga jisme sabhi views ki list hogi.
3. List me **`CodeWarden`** ko dhoondein aur uspe **Checkmark (✔)** laga dein.

```
+------------------------------------------+
|  [Explorer]                 ✔            |
|  [Search]                   ✔            |
|  [Source Control]           ✔            |
|  ...                                     |
|  [CodeWarden]               ✔ <-- Click! |
+------------------------------------------+
```

### Step 3: Bottom Status Bar Shortcut (Super Easy!)
VS Code ke bilkul neeche (Bottom-Left) status bar me ek icon dikhega:
```
$(shield) Security Guard: idle
```
Is status bar item par **1-click** karne se CodeWarden ka sidebar dashboard turant open ho jata hai!

### Step 4: Command Palette Shortcut
- Press karein: **`Ctrl + Shift + P`**
- Type karein: `Security Guard: Open Dashboard` aur **Enter** press karein.

---

## 🔑 3. Mistral AI API Key Setup

CodeWarden security patches generate karne ke liye Mistral AI ke free model **`codestral-latest`** ka use karta hai.

### Free Key Kaise Lein:
1. Browser me open karein: [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys/)
2. Apne Google / GitHub account se login karein aur **Create new key** par click karein.
3. Key copy karein (yeh `mstrl_...` se shuru hoti hai).

### Key Save Karne ke 2 Tareeqe:

**Tareeqa 1: CodeWarden Sidebar ke Dabbe me (Sabse Aasan)**
1. CodeWarden sidebar open karein.
2. Upar **Mistral AI Key** ka box (dabba) dikhega:
   ```
   Mistral AI Key         [ Missing ]
   [ mstrl_ZbBc7Bv... ]   [ Save ]
   ```
3. Key paste karke **Save** button dabayein. Badge turant green ho jayega: `[ Configured ]`!

**Tareeqa 2: `backend/.env` file me**
`backend/.env` file open karke ye line save kar dein:
```env
MISTRAL_API_KEY=mstrl_ZbBc7BvOyp1tOUWJnIqmm7C1hN7U0P40_3IkJsA
MISTRAL_MODEL=codestral-latest
```

---

## 🛡️ 4. Code Scan Kaise Karein

CodeWarden aapke Python code me multi-engine security scan karta hai:
- **Bandit** — AST based security vulnerability scanner.
- **Secrets Detector** — Hardcoded API keys, JWT tokens, AWS credentials detect karta hai.
- **Pip-Audit** — Outdated aur vulnerable dependencies (CVEs) detect karta hai.

### Scan Chalane ke Tareeqe:
1. **Sidebar se Pure Workspace ka Scan:**
   - Sidebar me blue button dabayein:
     ```
     [ 🛡️ Scan Entire Workspace ]
     ```
   - Status banner animate hoga: `Scanning Workspace... Running Bandit, AST, Secrets & pip-audit...`
2. **Auto-Scan on Save:**
   - Kisi bhi `.py` file ko edit karke **`Ctrl + S`** save karein. CodeWarden background me automatically scan kar lega.

---

## ⚡ 5. AI Patch & Sandbox Verification Kaise Use Karein

Jab CodeWarden koi vulnerability find karta hai:

1. Sidebar me vulnerability card dikhega jisme severity tag (High, Critical, Medium), file name, aur line number hoga.
2. Card ke andar **`⚡ Fix with AI`** button par click karein:
   ```
   +----------------------------------------------------+
   | CRITICAL                       vulnapp/app.py:14   |
   | sql injection                                      |
   | Possible SQL injection vector through string form  |
   |                                                    |
   | [ 🔍 View ]          [ ⚡ Fix with AI ]            |
   +----------------------------------------------------+
   ```
3. **Patcher Pipeline automatically execute hogi:**
   - **Triage & Planner:** AI vulnerability ko diagnose karta hai aur safe fix plan banata hai.
   - **Patcher Agent:** AI security patched code aur regression test likhta hai.
   - **Docker Sandbox Verification (7 Checks):** CodeWarden patch ko isolated container me chala kar test karta hai:
     1. Syntax correctness (AST parse)
     2. Bandit re-scan (No new vulnerabilities)
     3. Security test execution
     4. Semantics preservation
     5. Dependency integrity
     6. No secrets introduced
     7. Sandbox exit status == 0
4. **Side-by-Side Diff View:**
   - Screen par Split Diff viewer khulega jisme Original Code vs AI Patched Code dikhega.
   - Output pane me full rationale dikhega:
     - *What was wrong*
     - *Why it matters*
     - *What changed*
     - *Checks passed in sandbox*
5. Right-bottom popup me **"Accept"** dabane par patch aapke original file me safely apply ho jayega!

---

## 🧪 6. Seeded Vulnerable Demo App se Test Karein

Test karne ke liye repo me already ek test vulnerable app maujood hai:
📁 **`demo_apps/vulnapp/app.py`**

Is app me yeh common vulnerabilities seeded hain:
1. **SQL Injection (`/user`):** Unsanitized query string formatting.
2. **Command Injection (`/ping`):** `subprocess.run(f"ping {host}", shell=True)`.
3. **Path Traversal (`/download`):** Unchecked file path concatenation.
4. **Insecure Deserialization (`/load_config`):** `yaml.load(data, Loader=yaml.Loader)`.
5. **Hardcoded Secrets:** Leaked AWS secret key inside source code.

👉 Inhe scan karne ke liye sidebar me **"Scan Entire Workspace"** dabayein aur har ek ka AI fix test karein!

---

## 🛠️ 7. Troubleshooting & FAQs

### Q1: Sidebar me "Backend: Offline" dikh raha hai?
**Fix:**
- Sidebar me green button **[ 🚀 1-Click Start Backend Server ]** dabayein.
- Ya root folder me **`start.bat`** par double click karein.
- Check karein ki port 8765 busy toh nahi hai.

### Q2: "Docker: Missing" badge aa raha hai?
**Fix:**
- Docker Desktop app ko start karein aur engine running hone tak wait karein.
- Phir terminal me run karein: `docker image inspect codewarden-sandbox`.
- Agar build karna ho toh: `docker build -t codewarden-sandbox -f backend\Dockerfile.sandbox backend\`

### Q3: "Invalid API Key" ya "403 Forbidden" error aa raha hai?
**Fix:**
- Mistral ke free tier me `mistral-large-latest` allowed nahi hai. CodeWarden automatically **`codestral-latest`** use karta hai.
- Sidebar ke **Mistral AI Key** dabbe me apni nayi key paste karke **Save** dabayein. Key ke aage peeche quotes (`"`) na lagayein (CodeWarden automatically quotes trim kar deta hai).

### Q4: Extension ko manually build / reinstall kaise karein?
Terminal me yeh commands chalayein:
```powershell
cd extension
npm run compile
npx @vscode/vsce package --no-dependencies
code --install-extension codewarden-0.1.0.vsix --force
```
Uske baad VS Code me `Ctrl + Shift + P` -> `Developer: Reload Window` karein.

---

🎉 **Badhaai ho! Aapka CodeWarden system ab 100% ready hai!**
Kisi bhi sawal ya madad ke liye aap project terminal aur logs check kar sakte hain.
