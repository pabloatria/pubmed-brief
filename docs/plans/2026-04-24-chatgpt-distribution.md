# ChatGPT Distribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the `pubmed-brief` skill so the same GitHub repo serves both Claude users (install the skill) and ChatGPT users (set up a Custom GPT that uploads the same `build_pdf.py` + fonts from this repo).

**Architecture:** Single source of truth. No duplicated `build_pdf.py`. Add a `chatgpt/` subfolder with the three Custom-GPT artifacts (setup guide, GPT instructions, OpenAPI spec). One small code change to `build_pdf.py`'s font path resolver so it works with ChatGPT's flat `/mnt/data/` Knowledge layout. README gains an Install section with two platform paths.

**Tech Stack:** Python 3.10+ (existing); ReportLab (existing); OpenAPI 3.1 (Custom GPT Actions); plain Markdown docs.

**Design reference:** `docs/plans/2026-04-24-chatgpt-distribution-design.md`

---

## Task 1: Patch the font loader to find fonts in both `./fonts/` and flat `./`

**Files:**
- Modify: `scripts/build_pdf.py` (font-registration block, near top)

**Step 1: Write the failing test**

Create `/tmp/test_flat_font_layout.py`:

```python
"""Simulate ChatGPT's flat Knowledge upload: build_pdf.py and the TTF files
live in the same flat directory with no 'fonts/' subfolder."""
import os, shutil, sys, tempfile, json

REPO = "/Users/pabloatria/Downloads/pubmed-brief"
tmp = tempfile.mkdtemp(prefix="chatgpt-sim-")
# Copy build_pdf.py into the flat temp dir
shutil.copy(os.path.join(REPO, "scripts/build_pdf.py"), tmp)
# Copy the 4 TTF files flat (no 'fonts/' subfolder)
for fname in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
              "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"):
    shutil.copy(os.path.join(REPO, "scripts/fonts", fname), tmp)

# Minimal brief + summaries with a non-ASCII author name
brief = {
    "query": "test", "generated_at": "2026-04-24T00:00:00",
    "recent": [{"pmid": "1", "title": "T", "authors": ["Revilla-León M"],
                "journal": "J", "year": "2026",
                "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/"}],
    "cited": [],
}
summaries = {"synthesis": "β-TCP μm α ≤ 0.05 — Wójcik, Müller.", "recent": {}, "cited": {}}
with open(os.path.join(tmp, "brief.json"), "w") as f: json.dump(brief, f)
with open(os.path.join(tmp, "summaries.json"), "w") as f: json.dump(summaries, f)

# Import from the flat location so _FONT_DIR resolves there
sys.path.insert(0, tmp)
if "build_pdf" in sys.modules: del sys.modules["build_pdf"]
import build_pdf
out = os.path.join(tmp, "out.pdf")
build_pdf.build_pdf(os.path.join(tmp, "brief.json"),
                    os.path.join(tmp, "summaries.json"), out)
assert os.path.exists(out) and os.path.getsize(out) > 5000

# Verify DejaVu was used (not Helvetica fallback) by checking the PDF's
# font table.
import fitz
d = fitz.open(out)
fonts_found = set()
for i in range(d.page_count):
    for font in d[i].get_fonts():
        fonts_found.add(font[3])  # basename
# If DejaVu is embedded we should see it referenced; otherwise "Helvetica"
assert any("DejaVu" in f for f in fonts_found), \
    f"flat-layout font fallback did not load DejaVu; fonts: {fonts_found}"
print(f"OK: flat-layout DejaVu load succeeded. fonts: {fonts_found}")
```

**Step 2: Run the test to verify it fails**

```bash
python3 /tmp/test_flat_font_layout.py
```

Expected: prints `[pdf] WARNING: bundled fonts not found ...` followed by assertion failure, because the current `_register_bundled_fonts()` only probes `Path(__file__).resolve().parent / "fonts"` and the flat layout has no `fonts/` subdir.

**Step 3: Modify `scripts/build_pdf.py` — the font-registration block**

Find:

```python
_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_REGISTERED = False


def _register_bundled_fonts() -> str:
```

Replace with:

```python
# Font files live next to build_pdf.py in one of two layouts:
#   - ./fonts/<file>.ttf   (repo layout, Claude install)
#   - ./<file>.ttf         (flat layout, ChatGPT Knowledge upload — all
#                           uploaded files end up in /mnt/data/ side-by-side)
# We probe both, prefer the subfolder, fall back to Helvetica with a warning
# if neither location has the fonts.
_FONT_DIR_PRIMARY = Path(__file__).resolve().parent / "fonts"
_FONT_DIR_FALLBACK = Path(__file__).resolve().parent
_FONT_REGISTERED = False


def _find_font(filename: str) -> Optional[Path]:
    for d in (_FONT_DIR_PRIMARY, _FONT_DIR_FALLBACK):
        p = d / filename
        if p.exists():
            return p
    return None


def _register_bundled_fonts() -> str:
```

Then in the body of `_register_bundled_fonts`, replace the four `TTFont(... str(_FONT_DIR / "XYZ.ttf"))` lines with lookups that use `_find_font()`. If any lookup returns `None`, raise a `FileNotFoundError` and let the existing `except` block fall back to Helvetica.

Also add `from typing import Optional` to the imports at the top of the file if not already present.

**Step 4: Run the test to verify it passes**

```bash
python3 /tmp/test_flat_font_layout.py
```

Expected: prints `OK: flat-layout DejaVu load succeeded. fonts: {...}` with at least one `DejaVu*` entry. No warning about bundled fonts missing.

**Step 5: Verify the existing Claude layout still works**

```bash
python3 -c "
import sys; sys.path.insert(0, '/Users/pabloatria/Downloads/pubmed-brief/scripts')
if 'build_pdf' in sys.modules: del sys.modules['build_pdf']
import build_pdf
name = build_pdf._register_bundled_fonts()
print(f'registered: {name}')
assert name == 'Body', f'expected Body, got {name}'
"
```

Expected: `registered: Body`. Confirms the repo layout (with `fonts/` subfolder) still resolves correctly.

**Step 6: Commit**

```bash
cd /Users/pabloatria/Downloads/pubmed-brief
git add scripts/build_pdf.py
git commit -m "build_pdf: find bundled fonts in both ./fonts/ and flat ./

ChatGPT's Custom GPT Knowledge upload is flat — every uploaded file lands
in /mnt/data/ with no subdirectory structure. Add a fallback probe next
to build_pdf.py so the same script works whether installed as the Claude
skill (fonts in ./fonts/) or uploaded to a Custom GPT (fonts flat)."
```

---

## Task 2: Create `chatgpt/openapi.yaml` (no semantic changes)

**Files:**
- Create: `chatgpt/openapi.yaml`

The existing draft at `/Users/pabloatria/Downloads/Pubmed Skill/GPT/pubmed_action_openapi.yaml` is already validated and working in ChatGPT's Actions parser. Copy it verbatim into the repo.

**Step 1: Copy the file**

```bash
mkdir -p /Users/pabloatria/Downloads/pubmed-brief/chatgpt
cp "/Users/pabloatria/Downloads/Pubmed Skill/GPT/pubmed_action_openapi.yaml" \
   /Users/pabloatria/Downloads/pubmed-brief/chatgpt/openapi.yaml
```

**Step 2: Sanity-check it's valid YAML and an OpenAPI 3.1 doc**

```bash
python3 -c "
import yaml
with open('/Users/pabloatria/Downloads/pubmed-brief/chatgpt/openapi.yaml') as f:
    s = yaml.safe_load(f)
assert s['openapi'].startswith('3.1'), f'unexpected openapi version: {s[\"openapi\"]}'
assert s['paths']['/esearch.fcgi']['get']['operationId'] == 'searchPubMed'
print('openapi ok:', s['info']['title'])
"
```

Expected: `openapi ok: PubMed Search via NCBI eutils`

**Step 3: Commit — deferred, commit with Tasks 3 & 4 as one unit**

---

## Task 3: Write `chatgpt/CUSTOM_GPT_INSTRUCTIONS.md` (rewrite of old draft)

**Files:**
- Create: `chatgpt/CUSTOM_GPT_INSTRUCTIONS.md`

**Key corrections vs. the old draft:**
- Use `generated_at` (not `generated_on`) — matches `build_pdf.py`.
- Use `pmc.ncbi.nlm.nih.gov/articles/PMCID/` (new domain post-2024 NCBI migration).
- Instruct the GPT to emit `authors` as `list[str]` (the form `build_pdf.py` prefers, though `format_authors` now tolerates strings too).
- Note that the bundled fonts must be in the same `/mnt/data/` directory as `build_pdf.py` for Unicode to render; this is automatic if the user follows SETUP.md.
- Drop the `subprocess` pattern in favor of `%run` or `python -m` since subprocess on `/mnt/data/*.py` sometimes fails due to perms; show both and recommend the simpler one.

**Step 1: Create the file** — content in the appendix below (A1).

**Step 2: Read it back and confirm structure**

```bash
grep -c "^##" /Users/pabloatria/Downloads/pubmed-brief/chatgpt/CUSTOM_GPT_INSTRUCTIONS.md
```

Expected: 4 or more top-level `##` sections (When to use, Your tools, Workflow, Edge cases).

**Step 3: Commit deferred.**

---

## Task 4: Write `chatgpt/SETUP.md` (rewrite of old draft)

**Files:**
- Create: `chatgpt/SETUP.md`

**Key corrections vs. the old draft:**
- Fix the `<your-username>` placeholder → `pabloatria`.
- Add a step to upload the four `.ttf` fonts alongside `build_pdf.py`.
- Add a "Publishing to the GPT Store" subsection (user explicitly asked for public visibility).
- Move the comparison table to SETUP.md's header so users see tradeoffs before committing to setup.
- Add a "Maintenance" section explicitly covering what to re-upload when upstream changes.

**Step 1: Create the file** — content in the appendix below (A2).

**Step 2: Read it back**

```bash
grep -E "^(##|###) " /Users/pabloatria/Downloads/pubmed-brief/chatgpt/SETUP.md
```

Expected: Section headers including "What you get", "Setup", "Publish to the GPT Store", "Maintenance", "Tradeoffs vs the Claude skill".

**Step 3: Commit deferred.**

---

## Task 5: Add "Install" section to README with two platform paths

**Files:**
- Modify: `README.md` (replace the existing "Install (macOS / Linux)" and "Use it" sections with a two-path "Install" section)

**Step 1: Read the current README install block**

```bash
grep -n "^## Install" /Users/pabloatria/Downloads/pubmed-brief/README.md
grep -n "^## Use it" /Users/pabloatria/Downloads/pubmed-brief/README.md
```

**Step 2: Replace the current install/use-it block with the new two-path section**

New content in appendix A3. Key points:
- Leads with "Pick your AI" and presents Claude + ChatGPT as equal peers.
- Claude path: unchanged install instructions (git clone + install.sh).
- ChatGPT path: one-line "click to use" with the public Custom GPT URL + link to `chatgpt/SETUP.md` for users who want their own.
- The "Use it" examples and manual-mode block remain below, applying to Claude only.

**Step 3: Update the repo-structure section**

In the same README, update the repo tree block to include `chatgpt/` and `docs/`. The current block is near line 137.

**Step 4: Verify rendered Markdown**

```bash
head -80 /Users/pabloatria/Downloads/pubmed-brief/README.md
```

Visually scan: Install section present near top, two platform blocks under it, ChatGPT block has a link to `chatgpt/SETUP.md`.

**Step 5: Commit Tasks 2–5 together.**

```bash
cd /Users/pabloatria/Downloads/pubmed-brief
git add chatgpt/ README.md
git commit -m "Add ChatGPT Custom GPT distribution path

Single source of truth: the shared scripts/build_pdf.py + scripts/fonts/*.ttf
already in the repo power both the Claude skill and a ChatGPT Custom GPT.
New chatgpt/ folder holds the three platform-specific artifacts (SETUP.md,
CUSTOM_GPT_INSTRUCTIONS.md, openapi.yaml) — rewrites of the earlier drafts
that fix stale field names (generated_on -> generated_at), the old PMC
domain, and the missing font upload step.

README gains a two-path Install section so users land on their platform in
one scroll. GPT Store URL is a placeholder until the user publishes."
```

---

## Task 6: Full end-to-end verification

**Files:**
- None modified — pure verification.

**Step 1: Run the Claude path (live NCBI)**

```bash
cd /Users/pabloatria/Downloads/pubmed-brief
WORKDIR="${TMPDIR:-/tmp}"
python3 scripts/search_articles.py "endocrown OR endocrowns" \
  --email "atria.pablo@gmail.com" --per-section 2 \
  --out "$WORKDIR/brief.json" 2>&1 | tail -5
```

Expected: `[search] Wrote ...brief.json`, no warnings about partial enrichment.

**Step 2: Build the PDF from that brief with minimal summaries**

```bash
python3 -c "
import json
with open('$WORKDIR/brief.json') as f: b = json.load(f)
summaries = {'synthesis':'Test synthesis.', 'recent':{}, 'cited':{}}
for sec in ('recent','cited'):
    for a in b[sec]:
        summaries[sec][a['pmid']] = {
            'background':'BG.', 'methods':'M.', 'results':'R.', 'clinical_takeaway':'CT.'}
with open('$WORKDIR/summaries.json','w') as f: json.dump(summaries, f)
"
python3 scripts/build_pdf.py "$WORKDIR/brief.json" \
  --summaries "$WORKDIR/summaries.json" --out "$WORKDIR/claude-path.pdf"
ls -la "$WORKDIR/claude-path.pdf"
```

Expected: PDF > 20 KB, no stderr warnings.

**Step 3: Re-run the flat-layout test from Task 1**

```bash
python3 /tmp/test_flat_font_layout.py
```

Expected: still prints `OK: flat-layout DejaVu load succeeded.`.

**Step 4: Lint the OpenAPI**

```bash
python3 -c "
import yaml
with open('/Users/pabloatria/Downloads/pubmed-brief/chatgpt/openapi.yaml') as f:
    s = yaml.safe_load(f)
for op in ('searchPubMed','getArticleSummaries','getArticleAbstracts'):
    found = any(s['paths'][p]['get']['operationId'] == op for p in s['paths'])
    assert found, f'missing operationId: {op}'
print('openapi operations OK')
"
```

Expected: `openapi operations OK`.

**Step 5: Visually re-read README and SETUP.md**

```bash
sed -n '1,60p' /Users/pabloatria/Downloads/pubmed-brief/README.md
echo "===="
sed -n '1,60p' /Users/pabloatria/Downloads/pubmed-brief/chatgpt/SETUP.md
```

Confirm: README Install section present; SETUP.md leads with setup steps, not philosophy.

**Step 6: Push**

```bash
cd /Users/pabloatria/Downloads/pubmed-brief
git push
```

Expected: `main -> main` push succeeds. URL printed.

---

## Task 7 (deferred — user action): Publish GPT & update README URL

**User does:**
1. Opens ChatGPT, follows `chatgpt/SETUP.md`.
2. Publishes the Custom GPT to the **public GPT Store** (not "Only me" or "Anyone with link").
3. Copies the `chat.openai.com/g/g-XXXXX-pubmed-brief` URL that OpenAI assigns.
4. Sends the URL back — we do one more tiny commit to fill in the placeholder.

**Agent does on receiving URL:**

```bash
# Replace the placeholder in README.md with the real URL
cd /Users/pabloatria/Downloads/pubmed-brief
sed -i '' 's|https://chat.openai.com/g/g-XXXXX-pubmed-brief|<REAL_URL>|' README.md
git add README.md
git commit -m "docs: link to published PubMed Brief Custom GPT"
git push
```

---

## Appendix — full file contents

### A1. `chatgpt/CUSTOM_GPT_INSTRUCTIONS.md`

_(Full markdown body — see implementation notes below; mirrors the structure of the existing draft with the corrections listed in Task 3. Pending final write during implementation.)_

### A2. `chatgpt/SETUP.md`

_(Full markdown body — see Task 4 corrections. Pending final write during implementation.)_

### A3. README "Install" section

_(Replacement block for the existing "Install (macOS / Linux)" section in README.md. Pending final write during implementation.)_

---

## Risks / things to watch

- **Path(__file__) in ChatGPT:** if ChatGPT invokes `build_pdf.py` via `%run /mnt/data/build_pdf.py`, `__file__` should be set; verify Task 1's flat-layout test is a fair simulation.
- **ReportLab caches registered font names globally:** the Task 1 test deletes `sys.modules['build_pdf']` but ReportLab's `pdfmetrics` keeps the registered `Body` font from the previous import. If that causes the flat-test to pass spuriously, add an explicit `pdfmetrics.standardFonts` reset or subprocess-isolate the test.
- **The OpenAPI schema uses `https://eutils.ncbi.nlm.nih.gov` as the server:** if ChatGPT's Action sandbox can't reach it (unlikely but possible), the GPT will fail silently. SETUP.md's Step 3 has a "Test" button — document that step clearly.
