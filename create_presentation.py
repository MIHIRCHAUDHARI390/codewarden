import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_deck(output_path="CodeWarden_Presentation.pptx"):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette - Cyber Modern Tech
    C_BG = RGBColor(15, 23, 42)          # Deep Slate #0f172a
    C_CARD = RGBColor(30, 41, 59)        # Dark Slate Card #1e293b
    C_CARD_BORDER = RGBColor(51, 65, 85) # Slate 700 #334155
    C_BLUE = RGBColor(59, 130, 246)      # Neon Blue #3b82f6
    C_GREEN = RGBColor(16, 185, 129)     # Cyber Emerald #10b981
    C_AMBER = RGBColor(245, 158, 11)     # Warning Amber #f59e0b
    C_RED = RGBColor(239, 68, 68)        # Crimson Danger #ef4444
    C_PURPLE = RGBColor(168, 85, 247)    # Accent Purple #a855f7
    C_TEXT = RGBColor(248, 250, 252)     # White #f8fafc
    C_MUTED = RGBColor(148, 163, 184)    # Slate Muted #94a3b8

    def set_slide_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = C_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category_text="CODEWARDEN ARCHITECTURE"):
        # Category pill
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(8), Inches(0.4))
        tf = cat_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = category_text.upper()
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = C_BLUE

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.5), Inches(0.8))
        tf2 = title_box.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = title_text
        p2.font.size = Pt(24)
        p2.font.bold = True
        p2.font.color.rgb = C_TEXT

    def add_card(slide, left, top, width, height, bg_color=C_CARD, border_color=C_CARD_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = Pt(1.2)
        return card

    # ==========================================
    # SLIDE 1: Title Slide (Cover)
    # ==========================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1)

    # Decorative glow card behind title
    glow = add_card(s1, Inches(0.8), Inches(1.0), Inches(11.733), Inches(5.5), bg_color=RGBColor(20, 29, 50))

    # Badge
    badge = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.3), Inches(1.5), Inches(3.2), Inches(0.45))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(30, 58, 138)
    badge.line.color.rgb = C_BLUE
    p = badge.text_frame.paragraphs[0]
    p.text = "🛡️  AUTONOMOUS DEVSECOPS"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = RGBColor(191, 219, 254)
    p.alignment = PP_ALIGN.CENTER

    # Main Title
    tbox = s1.shapes.add_textbox(Inches(1.3), Inches(2.1), Inches(10.5), Inches(1.4))
    tf = tbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "CodeWarden"
    p.font.size = Pt(46)
    p.font.bold = True
    p.font.color.rgb = C_TEXT

    p2 = tf.add_paragraph()
    p2.text = "AI Security Guard for Python Developers"
    p2.font.size = Pt(22)
    p2.font.color.rgb = C_BLUE
    p2.space_before = Pt(8)

    # Core Philosophy Tagline
    tagbox = s1.shapes.add_textbox(Inches(1.3), Inches(3.7), Inches(10.5), Inches(0.9))
    tf = tagbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "“Nothing reaches you unless it passes objective checks.\nNothing changes your code unless you approve it.”"
    p.font.size = Pt(15)
    p.font.italic = True
    p.font.color.rgb = C_MUTED

    # 4 Feature Pills
    features = [
        ("VS Code Extension", "Sidebar Dashboard & QuickFix", C_BLUE),
        ("Multi-Agent AI", "LangGraph + Mistral Codestral", C_PURPLE),
        ("Docker Sandbox", "7 Automated Safety Verification Checks", C_GREEN),
        ("Human Control", "Side-by-Side Diff & 1-Click Accept", C_AMBER)
    ]
    pill_w = Inches(2.65)
    for i, (title, sub, col) in enumerate(features):
        px = Inches(1.3) + i * (pill_w + Inches(0.35))
        py = Inches(4.9)
        c = add_card(s1, px, py, pill_w, Inches(1.2), bg_color=C_CARD)
        tb = s1.shapes.add_textbox(px, py + Inches(0.1), pill_w, Inches(1.0))
        tf = tb.text_frame
        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(13)
        p.font.color.rgb = col
        p.alignment = PP_ALIGN.CENTER
        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.size = Pt(10)
        p2.font.color.rgb = C_MUTED
        p2.alignment = PP_ALIGN.CENTER
        p2.space_before = Pt(4)

    # ==========================================
    # SLIDE 2: The Core Problem (DevSecOps Gap)
    # ==========================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "The Critical Security Dilemma in Modern Development", "PROBLEM STATEMENT")

    problems = [
        ("1. Static Analysis Noise & Fatigue", 
         "Traditional linters and SAST tools (Bandit, Semgrep) produce overwhelming noise and false alarms.\n\nDevelopers ignore warnings or disable security checks entirely because linters report problems without providing tested solutions.",
         C_RED),
        ("2. Blind AI Hallucinations & Breakages", 
         "Standard AI coding assistants (Copilot, ChatGPT) generate fixes that look plausible but hallucinate non-existent APIs, introduce breaking syntax changes, or silently weaken security boundaries.",
         C_AMBER),
        ("3. Late-Stage Security Reviews", 
         "Security audits happen weeks after pull requests are merged. Fixing architectural vulnerabilities in production costs 10x-30x more time and engineer hours than catching them inside the IDE.",
         C_PURPLE)
    ]

    card_w = Inches(3.64)
    for i, (title, desc, col) in enumerate(problems):
        cx = Inches(0.8) + i * (card_w + Inches(0.4))
        cy = Inches(1.8)
        card = add_card(s2, cx, cy, card_w, Inches(4.9))
        
        # Color accent header
        accent = s2.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, cy, card_w, Inches(0.1))
        accent.fill.solid()
        accent.fill.fore_color.rgb = col
        accent.line.fill.background()

        tb = s2.shapes.add_textbox(cx + Inches(0.2), cy + Inches(0.3), card_w - Inches(0.4), Inches(4.3))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(16)
        p.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(13)
        p2.font.color.rgb = C_TEXT
        p2.space_before = Pt(14)

    # ==========================================
    # SLIDE 3: The CodeWarden Solution
    # ==========================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3)
    add_header(s3, "CodeWarden: Autonomous IDE Security with Zero Hallucination", "OUR SOLUTION")

    pillars = [
        ("Multi-Engine Detection", 
         "• AST-level Python vulnerability scanning (Bandit).\n• Real-time hardcoded secrets & API key detection.\n• Dependency CVE vulnerability audit (pip-audit).\n• Instant Scan on Save + Entire Workspace Scan.",
         C_BLUE),
        ("LangGraph Multi-Agent AI", 
         "• Triage Agent: Root cause security diagnosis.\n• Planner Agent: Least-privilege safe fix strategy.\n• Patcher Agent: Context-aware security patch & test.\n• Reviewer Agent: Validates semantic code safety.",
         C_PURPLE),
        ("Isolated Docker Sandbox", 
         "• Every patch is applied inside an isolated container.\n• 7 automated objective verification gates executed.\n• Regression test added and proven to pass.\n• Zero broken code reaches the developer's eyes.",
         C_GREEN),
        ("Developer-in-the-Loop", 
         "• Native VS Code Split Diff viewer.\n• Full reasoning output (What, Why, What Changed).\n• Explicit 'Accept' or 'Decline' control.\n• Zero unexpected auto-commits or silent merges.",
         C_AMBER)
    ]

    for i, (title, desc, col) in enumerate(pillars):
        row = i // 2
        col_idx = i % 2
        cx = Inches(0.8) + col_idx * (Inches(5.7) + Inches(0.33))
        cy = Inches(1.8) + row * (Inches(2.35) + Inches(0.25))
        
        card = add_card(s3, cx, cy, Inches(5.7), Inches(2.35))
        
        # Left color bar
        bar = s3.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, cy, Inches(0.12), Inches(2.35))
        bar.fill.solid()
        bar.fill.fore_color.rgb = col
        bar.line.fill.background()

        tb = s3.shapes.add_textbox(cx + Inches(0.3), cy + Inches(0.15), Inches(5.2), Inches(2.0))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(16)
        p.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(12)
        p2.font.color.rgb = C_TEXT
        p2.space_before = Pt(8)

    # ==========================================
    # SLIDE 4: Architecture & Workflow
    # ==========================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "End-to-End System Architecture & Agent Flow", "SYSTEM ARCHITECTURE")

    steps = [
        ("1. VS Code Extension", "Scans active Python files & workspace.\nReports findings to Activity Bar Sidebar.", C_BLUE),
        ("2. FastAPI Backend", "Runs on port 8765.\nPersists runs & findings in SQLite database.", C_PURPLE),
        ("3. AI Multi-Agent Loop", "LangGraph orchestrates Mistral Codestral\n(Triage -> Planner -> Patcher -> Reviewer).", C_AMBER),
        ("4. Docker Sandbox", "Container builds patch, executes tests,\nand enforces 7 automated validation checks.", C_GREEN),
        ("5. Verified Diff & Decision", "Developer reviews side-by-side diff,\naudits evidence, and clicks Accept to apply.", C_BLUE)
    ]

    step_w = Inches(2.15)
    for i, (stitle, sdesc, scol) in enumerate(steps):
        sx = Inches(0.8) + i * (step_w + Inches(0.24))
        sy = Inches(2.0)
        card = add_card(s4, sx, sy, step_w, Inches(4.6))
        
        # Top banner
        banner = s4.shapes.add_shape(MSO_SHAPE.RECTANGLE, sx, sy, step_w, Inches(0.12))
        banner.fill.solid()
        banner.fill.fore_color.rgb = scol
        banner.line.fill.background()

        tb = s4.shapes.add_textbox(sx + Inches(0.12), sy + Inches(0.3), step_w - Inches(0.24), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = stitle
        p.font.bold = True
        p.font.size = Pt(14)
        p.font.color.rgb = scol

        p2 = tf.add_paragraph()
        p2.text = sdesc
        p2.font.size = Pt(11)
        p2.font.color.rgb = C_TEXT
        p2.space_before = Pt(10)

    # ==========================================
    # SLIDE 5: The 7 Sandbox Verification Checks
    # ==========================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "The 7 Automated Sandbox Verification Checks", "QUALITY & TRUST ENFORCEMENT")

    checks = [
        ("Check 1: Syntax & AST Integrity", "Parsed using Python AST parser to prove zero syntax errors, broken indentations, or invalid symbols.", C_GREEN),
        ("Check 2: Linter Re-Scan (Bandit)", "Re-runs security scanner in sandbox; confirms the reported vulnerability is gone and ZERO new issues created.", C_GREEN),
        ("Check 3: Regression Test Execution", "Executes the auto-generated security regression test (`test_sec_*.py`) in container to prove the fix works.", C_GREEN),
        ("Check 4: Semantic Logic Preservation", "Validates that existing application routes, functions, and parameters maintain original behavior without breakages.", C_BLUE),
        ("Check 5: Dependency Safety Check", "Ensures the patch does not introduce unpinned, deprecated, or vulnerable third-party dependencies.", C_BLUE),
        ("Check 6: Secret & Token Protection", "Verifies that hardcoded keys, tokens, or credentials are never added into patched source files.", C_AMBER),
        ("Check 7: Sandbox Zero Exit Status", "Ensures container execution completes cleanly with return code 0, zero runtime exceptions, and clean stdout.", C_AMBER)
    ]

    for i, (ctitle, cdesc, ccol) in enumerate(checks):
        cy = Inches(1.6) + i * Inches(0.76)
        card = add_card(s5, Inches(0.8), cy, Inches(11.733), Inches(0.66))
        
        tag = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), cy + Inches(0.12), Inches(0.4), Inches(0.4))
        tag.fill.solid()
        tag.fill.fore_color.rgb = ccol
        tag.line.fill.background()
        p = tag.text_frame.paragraphs[0]
        p.text = "✓"
        p.font.bold = True
        p.font.size = Pt(14)
        p.font.color.rgb = C_TEXT
        p.alignment = PP_ALIGN.CENTER

        tb = s5.shapes.add_textbox(Inches(1.6), cy + Inches(0.08), Inches(10.7), Inches(0.5))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = f"{ctitle} — "
        p.font.bold = True
        p.font.size = Pt(13)
        p.font.color.rgb = ccol
        
        run = p.add_run()
        run.text = cdesc
        run.font.bold = False
        run.font.size = Pt(12)
        run.font.color.rgb = C_TEXT

    # ==========================================
    # SLIDE 6: Seeded Vulnerability Detections
    # ==========================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "Demonstrated Vulnerabilities & AI Fix Capabilities", "VULNERABILITY BENCHMARK (VULNAPP)")

    vulns = [
        ("SQL Injection", "CRITICAL", "Replaces raw string interpolation (`f'SELECT...'`) with safe parameterized queries (`cursor.execute(sql, (param,))`).", C_RED),
        ("Command Injection", "CRITICAL", "Eliminates `shell=True` in `subprocess.run`; uses safe argument lists and `shlex.quote` boundaries.", C_RED),
        ("Path Traversal", "HIGH", "Replaces direct string join with `os.path.abspath` validation & boundary containment checks to prevent `../` attacks.", C_AMBER),
        ("Insecure Deserialization", "HIGH", "Replaces vulnerable `yaml.load(..., Loader=yaml.Loader)` with safe `yaml.safe_load(data)`.", C_AMBER),
        ("Hardcoded Secrets", "MEDIUM", "Detects leaked AWS keys/JWTs; redacts values and replaces with secure `os.environ.get()` retrieval.", C_BLUE),
        ("Vulnerable Dependencies", "MEDIUM", "Audits `requirements.txt` via `pip-audit`; flags known CVEs (e.g. PyYAML <= 5.3.1) with upgrade path.", C_BLUE)
    ]

    for i, (vname, vsev, vfix, vcol) in enumerate(vulns):
        row = i // 3
        col_idx = i % 3
        vx = Inches(0.8) + col_idx * (Inches(3.75) + Inches(0.24))
        vy = Inches(1.8) + row * (Inches(2.4) + Inches(0.25))

        card = add_card(s6, vx, vy, Inches(3.75), Inches(2.4))
        
        # Severity Badge
        badge = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, vx + Inches(0.2), vy + Inches(0.2), Inches(1.2), Inches(0.35))
        badge.fill.solid()
        badge.fill.fore_color.rgb = vcol
        badge.line.fill.background()
        p = badge.text_frame.paragraphs[0]
        p.text = vsev
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = C_TEXT
        p.alignment = PP_ALIGN.CENTER

        tb = s6.shapes.add_textbox(vx + Inches(0.2), vy + Inches(0.65), Inches(3.35), Inches(1.6))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = vname
        p.font.bold = True
        p.font.size = Pt(15)
        p.font.color.rgb = C_TEXT

        p2 = tf.add_paragraph()
        p2.text = vfix
        p2.font.size = Pt(11)
        p2.font.color.rgb = C_MUTED
        p2.space_before = Pt(6)

    # ==========================================
    # SLIDE 7: 1-Click DX & Future Roadmap
    # ==========================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7)
    add_header(s7, "Developer Experience & Product Roadmap", "THE ROAD AHEAD")

    # Left: 1-Click DX
    c1 = add_card(s7, Inches(0.8), Inches(1.8), Inches(5.7), Inches(4.9))
    tb1 = s7.shapes.add_textbox(Inches(1.1), Inches(2.0), Inches(5.1), Inches(4.4))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "⚡ 1-Click Frictionless Setup"
    p.font.bold = True
    p.font.size = Pt(18)
    p.font.color.rgb = C_GREEN

    items_left = [
        "• 1-Click Startup: Double click `start.bat` or press the green button in VS Code sidebar.",
        "• Automatic Environment: Checks Docker, pulls sandbox, and configures `.venv` automatically.",
        "• Port Self-Healing: Automatically detects & releases busy ports (e.g. port 8765 WinError 10013).",
        "• Dynamic Root Resolution: Works seamlessly from workspace root or any subfolder.",
        "• Instant API Key Box: Paste free Mistral Codestral key right in the sidebar dashboard."
    ]
    for item in items_left:
        p = tf1.add_paragraph()
        p.text = item
        p.font.size = Pt(12)
        p.font.color.rgb = C_TEXT
        p.space_before = Pt(10)

    # Right: Future Roadmap
    c2 = add_card(s7, Inches(6.833), Inches(1.8), Inches(5.7), Inches(4.9))
    tb2 = s7.shapes.add_textbox(Inches(7.133), Inches(2.0), Inches(5.1), Inches(4.4))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "🚀 Future Horizons & Roadmap"
    p.font.bold = True
    p.font.size = Pt(18)
    p.font.color.rgb = C_BLUE

    items_right = [
        "• Multi-Language Expansion: Extend support to TypeScript, JavaScript, Go, and Rust.",
        "• GitHub Action Bot: Auto-generate sandbox-verified PR patches on every security alert.",
        "• Custom Corporate Rulesets: Enterprise custom policies, OWASP Top 10, and CIS benchmarks.",
        "• Auto Regression Test Suite: Permanent regression test retention to prevent future regressions.",
        "• Security Posture Analytics: Team dashboard displaying MTTR (Mean Time to Remediation)."
    ]
    for item in items_right:
        p = tf2.add_paragraph()
        p.text = item
        p.font.size = Pt(12)
        p.font.color.rgb = C_TEXT
        p.space_before = Pt(10)

    prs.save(output_path)
    print(f"Presentation saved successfully to {output_path}")

if __name__ == "__main__":
    out = "CodeWarden_Presentation.pptx"
    if len(sys.argv) > 1:
        out = sys.argv[1]
    create_deck(out)
