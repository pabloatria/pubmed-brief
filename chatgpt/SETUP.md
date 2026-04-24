# PubMed Brief — ChatGPT Custom GPT Setup

**Audience:** you want to create your own Custom GPT version of PubMed Brief (either for personal use or to share with your own audience).

**Not looking to set anything up?** If you just want to *use* PubMed Brief inside ChatGPT, use the published Custom GPT linked in the main [README](../README.md) — no setup required. This file is only for people who want their own copy.

---

This is the ChatGPT-compatible version of the `pubmed-brief` Claude skill. It produces the same branded PDF output (teal #0F4C5C / bronze #B08D57 / beige #F5EFE6) using the same `build_pdf.py` generator, running inside ChatGPT via a Custom GPT with one OpenAPI Action.

**Time to set up:** ~10 minutes.
**Cost:** $0 incremental — requires an existing ChatGPT Plus subscription, no additional fees.

## Tradeoffs vs. the Claude skill

| Feature                         | Claude skill                    | ChatGPT Custom GPT                            |
|---------------------------------|---------------------------------|------------------------------------------------|
| Auto-trigger from any chat      | ✅ via SKILL.md description      | ⚠️ Only when the user is inside the Custom GPT  |
| True citation counts            | ✅ via Europe PMC                | ❌ Estimated from article age + journal + PMC  |
| PMC full-text fetch             | ✅ via Europe PMC XML            | ⚠️ Abstracts only                              |
| Unicode in author names         | ✅ (bundled DejaVu)              | ✅ (same bundled DejaVu, uploaded to Knowledge) |
| Install steps                   | 1 line (git clone + install.sh) | ~10 minutes in ChatGPT UI                      |
| PDF visual identity             | Identical                       | Identical (same `build_pdf.py`)                |
| Ongoing maintenance             | `git pull` updates everything   | Manual re-upload when `build_pdf.py` changes   |

If you need exact citation counts and full-text access, the Claude version is materially better. If your audience is on ChatGPT, the Custom GPT is good enough for clinical literature scanning.

## What your GPT will do

A Custom GPT named **PubMed Brief** that:

1. Takes a biomedical research topic as input.
2. Searches PubMed via NCBI's public E-utilities (no auth, no API key).
3. Pulls metadata and abstracts for the top 5 recent + top 5 most-cited (estimated) articles.
4. Generates structured 4-part summaries (background / methods / results / clinical takeaway).
5. Builds a branded PDF in Code Interpreter and delivers it as a downloadable file.

## Files you need

Either clone this repo or download these seven files individually:

**From `scripts/`:**
- `build_pdf.py`
- `fonts/DejaVuSans.ttf`
- `fonts/DejaVuSans-Bold.ttf`
- `fonts/DejaVuSans-Oblique.ttf`
- `fonts/DejaVuSans-BoldOblique.ttf`

**From this `chatgpt/` folder:**
- [`CUSTOM_GPT_INSTRUCTIONS.md`](./CUSTOM_GPT_INSTRUCTIONS.md) — paste into the GPT's Instructions field.
- [`openapi.yaml`](./openapi.yaml) — paste into the GPT's Actions → Schema field.

## Setup steps

### Step 1 — Create the Custom GPT

1. Go to <https://chatgpt.com> → click your name (bottom-left) → **My GPTs** → **Create a GPT**.
2. Click the **Configure** tab (not "Create" — the conversational builder is slower).
3. Fill in:
   - **Name:** `PubMed Brief`
   - **Description:** `Generate branded PDF literature briefs from PubMed. 5 most recent + 5 most cited articles with structured summaries and direct links.`
   - **Instructions:** paste the entire contents of [`CUSTOM_GPT_INSTRUCTIONS.md`](./CUSTOM_GPT_INSTRUCTIONS.md).
   - **Conversation starters** (suggested):
     - *What does the literature say about MODJAW and digital occlusion?*
     - *Latest research on zirconia veneers*
     - *Give me a literature brief on endocrowns*
     - *Evidence on oral microbiome and peri-implantitis*
4. **Capabilities** — enable:
   - ✅ Web Browsing (handles edge cases when NCBI rate-limits)
   - ✅ **Code Interpreter & Data Analysis** (REQUIRED for PDF generation)
   - DALL·E can stay disabled.

### Step 2 — Upload `build_pdf.py` + fonts to Knowledge

Scroll to **Knowledge** → **Upload files**. Upload **all five** files:

1. `build_pdf.py`
2. `DejaVuSans.ttf`
3. `DejaVuSans-Bold.ttf`
4. `DejaVuSans-Oblique.ttf`
5. `DejaVuSans-BoldOblique.ttf`

ChatGPT places every Knowledge file flat in `/mnt/data/`. `build_pdf.py`'s font loader probes that layout — Unicode author names like "Revilla-León" and Greek letters (β, μ, α) in abstracts render correctly.

If you skip the fonts, the PDF will still generate but non-ASCII characters degrade to blanks (the script prints a warning). Upload them.

### Step 3 — Add the PubMed Action

1. Scroll to **Actions** → **Create new action**.
2. Paste the entire contents of [`openapi.yaml`](./openapi.yaml) into the **Schema** field.
3. **Authentication:** leave as **None** (NCBI E-utilities requires no auth).
4. **Privacy policy URL:** `https://www.ncbi.nlm.nih.gov/home/about/policies/`
5. Click **Test** on the `searchPubMed` operation with a query like `term=endocrowns&db=pubmed&retmode=json&retmax=5&tool=pubmed-brief-gpt&email=test@example.com`. You should see a list of PMIDs. If you see an error, check that the server URL in the schema is `https://eutils.ncbi.nlm.nih.gov/entrez/eutils`.

### Step 4 — Save and test

1. Click **Update** / **Save**.
2. Test it with a real query: *"What does the literature say about endocrowns?"* The GPT should: search PubMed → fetch metadata → fetch abstracts → write structured summaries → build the PDF → deliver the file.
3. If anything fails, the most common issue is forgetting to upload one of the font files or typo'ing the Action schema paste.

### Step 5 — (Optional) Publish to the GPT Store

If you want others to find and use your GPT without setting their own up:

1. Back in the **Configure** tab, click **Update** (top-right) → **Share**.
2. Choose **Everyone**. This lists the GPT publicly in the GPT Store.
3. OpenAI assigns a permanent URL of the form `https://chatgpt.com/g/g-<hash>-<slug>`.
4. Before a GPT can be public, your ChatGPT profile needs a **verified builder name** — ChatGPT prompts you the first time.

Public GPTs go through automated review (minutes, not days).

## Maintenance — when the upstream repo updates

The canonical `build_pdf.py` and fonts live in this repo. Your Custom GPT does **not** auto-update; when upstream changes you need to re-upload.

Re-upload when:
- **`scripts/build_pdf.py` changed** → re-download, delete the old file from your GPT's Knowledge, upload the new one.
- **Font files changed** (rare) → same procedure.
- **`chatgpt/CUSTOM_GPT_INSTRUCTIONS.md` changed** → re-paste the updated content into your GPT's Instructions.
- **`chatgpt/openapi.yaml` changed** (rare) → re-paste into Actions → Schema.

The fastest way to tell: `git log -- scripts/build_pdf.py chatgpt/` on the cloned repo shows everything that has changed since you last synced. Consider subscribing to the repo's GitHub releases for notifications.
