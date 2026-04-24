# PubMed Brief — ChatGPT Custom GPT Setup

This is the ChatGPT-compatible version of the `pubmed-brief` Claude skill. It produces the same branded PDF output (teal #0F4C5C / bronze #B08D57 / beige #F5EFE6) using the same `build_pdf.py` generator, running inside ChatGPT via a Custom GPT with one OpenAPI Action.

**Time to set up:** ~10 minutes.
**Cost:** $0 incremental — requires an existing ChatGPT Plus subscription ($20/mo), no additional fees.

## Tradeoffs vs. the Claude skill

Read this before you start so you know what you're signing up for.

| Feature                         | Claude skill                    | ChatGPT Custom GPT                            |
|---------------------------------|---------------------------------|------------------------------------------------|
| Auto-trigger from any chat      | ✅ via SKILL.md description      | ⚠️ Only when the user is inside the Custom GPT  |
| True citation counts            | ✅ via Europe PMC                | ❌ Estimated from article age + journal + PMC  |
| PMC full-text fetch             | ✅ via Europe PMC XML            | ⚠️ Abstracts only                              |
| Unicode in author names         | ✅ (bundled DejaVu)              | ✅ (same bundled DejaVu, uploaded to Knowledge) |
| Install steps                   | 1 line (git clone + install.sh) | ~10 minutes in ChatGPT UI                      |
| PDF visual identity             | Identical                       | Identical (same `build_pdf.py`)                |
| Ongoing maintenance             | `git pull` updates everything   | Manual re-upload when `build_pdf.py` changes   |

If you need true citation counts and full-text access, the Claude version is materially better. If your audience is on ChatGPT, the Custom GPT is good enough for clinical literature scanning.

## What you get

A Custom GPT named **PubMed Brief** that:

1. Takes a biomedical research topic as input.
2. Searches PubMed via NCBI's public E-utilities (no auth, no API key).
3. Pulls metadata and abstracts for the top 5 recent + top 5 most-cited (estimated) articles.
4. Generates structured 4-part summaries (background / methods / results / clinical takeaway).
5. Builds a branded PDF in Code Interpreter and delivers it as a downloadable file.

## Setup

You need three files from this repo. Either clone the repo or download them individually:

- [`scripts/build_pdf.py`](../scripts/build_pdf.py)
- [`scripts/fonts/DejaVuSans.ttf`](../scripts/fonts/DejaVuSans.ttf)
- [`scripts/fonts/DejaVuSans-Bold.ttf`](../scripts/fonts/DejaVuSans-Bold.ttf)
- [`scripts/fonts/DejaVuSans-Oblique.ttf`](../scripts/fonts/DejaVuSans-Oblique.ttf)
- [`scripts/fonts/DejaVuSans-BoldOblique.ttf`](../scripts/fonts/DejaVuSans-BoldOblique.ttf)

And this folder's two text files:

- [`CUSTOM_GPT_INSTRUCTIONS.md`](./CUSTOM_GPT_INSTRUCTIONS.md) — paste into the GPT's Instructions field.
- [`openapi.yaml`](./openapi.yaml) — paste into the GPT's Actions → Schema field.

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

In the same Configure tab, scroll to **Knowledge** → **Upload files**. Upload **all five** files:

1. `build_pdf.py`
2. `DejaVuSans.ttf`
3. `DejaVuSans-Bold.ttf`
4. `DejaVuSans-Oblique.ttf`
5. `DejaVuSans-BoldOblique.ttf`

ChatGPT places all Knowledge files flat in `/mnt/data/`. `build_pdf.py`'s font loader probes that flat layout — Unicode author names like "Revilla-León" and Greek letters (β, μ, α) in abstracts will render correctly.

If you skip the fonts, the PDF will still generate but non-ASCII characters degrade to blanks (the script prints a warning). Just upload them.

### Step 3 — Add the PubMed Action

1. In Configure, scroll to **Actions** → **Create new action**.
2. Paste the entire contents of [`openapi.yaml`](./openapi.yaml) into the **Schema** field.
3. **Authentication:** leave as **None** (NCBI E-utilities requires no auth).
4. **Privacy policy URL:** `https://www.ncbi.nlm.nih.gov/home/about/policies/`
5. Click **Test** on the `searchPubMed` operation with a query like `term=endocrowns&db=pubmed&retmode=json&retmax=5&tool=pubmed-brief-gpt&email=test@example.com`. You should see a list of PMIDs. If you see an error, check that the server URL in the schema is `https://eutils.ncbi.nlm.nih.gov/entrez/eutils`.

### Step 4 — Save, test, then publish

1. Click **Update** / **Save**.
2. Test it with a real query: *"What does the literature say about endocrowns?"* The GPT should: search PubMed → fetch metadata → fetch abstracts → write structured summaries → build the PDF → deliver the file.
3. If anything fails, the most common issue is forgetting to upload one of the font files or typo'ing the Action schema paste.

## Publish to the GPT Store

To let anyone find and use your GPT:

1. Back in the **Configure** tab, click **Update** (top-right) → **Share**.
2. Choose **Everyone**. This lists the GPT publicly in the GPT Store — users can find it by searching "PubMed Brief" or your name.
3. OpenAI assigns a permanent URL of the form `https://chat.openai.com/g/g-XXXXXX-pubmed-brief`. Copy it.
4. Before a GPT can be published publicly, your ChatGPT profile needs a **verified builder name** — ChatGPT prompts you the first time.
5. Paste the assigned URL back in your repo's README so visitors can jump straight into the published GPT without setting their own up.

Public GPTs go through an automated review (minutes, not days). OpenAI occasionally rejects GPTs whose instructions mention specific other platforms in unfavorable ways; the Instructions file here is clean on this front.

## Maintenance

The single source of truth for `build_pdf.py` and the fonts lives in this repo. When the repo updates, the Custom GPT does not update automatically — you have to re-upload.

When to re-upload:
- **`build_pdf.py` changed** (check commits) → re-download from `scripts/build_pdf.py`, delete the old one in the GPT's Knowledge, upload the new one.
- **Font files changed** (rare) → same procedure.
- **Custom GPT instructions changed** (i.e. this repo's `chatgpt/CUSTOM_GPT_INSTRUCTIONS.md` got edits) → re-paste the updated content into the GPT's Instructions.
- **OpenAPI schema changed** (rare) → re-paste `chatgpt/openapi.yaml` into Actions → Schema.

The fastest way to tell: `git log -- scripts/build_pdf.py chatgpt/` on the cloned repo shows everything that's changed since you last synced.

## Promoting both versions

When you send someone to this skill:

- **Claude users** → `https://github.com/pabloatria/pubmed-brief` (install instructions in the main README).
- **ChatGPT users** → the published GPT Store URL (once you've completed "Publish to the GPT Store" above).

Same input, same PDF output, same brand. Audience on Claude gets richer citation/full-text data; audience on ChatGPT gets a zero-install experience.
