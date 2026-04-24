---
name: pubmed-brief
description: Search peer-reviewed biomedical literature on PubMed (with Europe PMC and Crossref enrichment) and produce a branded PDF brief with the top 5 most recent and top 5 most cited articles on a topic, each with structured summaries (background, methods, results, clinical takeaway) and direct links to PubMed, DOI, and free full text. Use this skill whenever the user asks to research, summarize, brief, or review the literature on any clinical, biomedical, dental, medical, pharmacological, or life-sciences topic — including phrases like "what does the literature say about X", "give me the latest research on Y", "find me papers on Z", "PubMed search", "literature review", "evidence summary", or "research brief". Trigger even if the user does not explicitly say "PDF" — a PDF deliverable is the standard output.
---

# PubMed Literature Brief

Produce a branded PDF brief summarizing peer-reviewed literature on a user-supplied topic. Two sections: 5 most recent (last 3 years) and 5 most cited (all-time). Each article includes a structured 4-part summary and direct links to PubMed, DOI, and PMC full text when available.

## When to use

- The user asks for a literature review, evidence summary, research brief, or PubMed search on any biomedical topic.
- The user wants to "see what's out there" on a clinical or scientific subject.
- The user names a specific drug, device, technique, condition, biomarker, or methodology and wants peer-reviewed evidence.

Do not use for: lay health questions answerable from general knowledge, news/blog searches (use web search), or non-biomedical topics.

## First-time setup (any machine, any OS)

The skill needs three Python packages: biopython, reportlab, requests. On the first run on a new machine, install them silently before anything else:

```bash
python3 -m pip install --quiet biopython reportlab requests 2>/dev/null || \
python3 -m pip install --quiet --break-system-packages biopython reportlab requests
```

This handles both clean Pythons and newer macOS Homebrew/system Pythons that block global installs by default.

Quick import check before running:
```bash
python3 -c "from Bio import Entrez; import reportlab, requests; print('ok')"
```

If this fails, surface the error to the user — don't proceed with the search.

## Workflow

The skill runs in four phases. Execute them in order — do not skip the search step and do not summarize from your own knowledge of the literature.

### Phase 1 — Clarify the query (only if genuinely ambiguous)

Most queries are clear enough to search directly. Only ask a clarifying question if the topic is so broad it would return thousands of unrelated hits ("dentistry", "cancer", "oral microbiome" alone) OR so vague the search terms aren't obvious. Otherwise, translate the user's request into a PubMed query and proceed.

A good PubMed query uses key concepts joined with AND, optionally with MeSH terms or field tags. Examples:
- User: "latest on oral microbiome and implant failure" → query: `oral microbiome AND (implant failure OR peri-implantitis)`
- User: "research on Curodont remineralization" → query: `Curodont OR (P11-4 AND remineralization)`
- User: "MODJAW and digital occlusion" → query: `MODJAW OR (jaw tracking AND digital occlusion)`
- User: "oral microbiome" (too broad) → query: `oral microbiome AND (periodontitis OR caries OR peri-implantitis OR dysbiosis)`

Confirm only the query if you're not sure — do not ask the user to pick a section count or formatting options.

### Phase 2 — Run the search pipeline

Use the platform-correct temp directory ($TMPDIR is set on macOS, /tmp on Linux):

```bash
WORKDIR="${TMPDIR:-/tmp}"
SKILL_DIR="<absolute path to this skill folder>"

python3 "$SKILL_DIR/scripts/search_articles.py" "QUERY HERE" \
  --email "your-email@domain.com" \
  --per-section 5 \
  --out "$WORKDIR/brief.json"
```

Do not hardcode `/tmp/` — `$TMPDIR` is the macOS convention (resolves to something like `/var/folders/.../T/`) and the script writes there cleanly.

The script returns JSON with two arrays — `recent` and `cited` — each containing 5 articles with fields: `pmid`, `doi`, `pmcid`, `title`, `authors`, `journal`, `year`, `abstract`, `full_text` (when open access), `citations`, `pubmed_url`, `doi_url`, `pmc_url`.

The script handles PubMed retrieval, Europe PMC citation counts and full-text fetch, and Crossref fallback automatically. It takes 30–90 seconds depending on how many articles have open-access full text.

If the script returns fewer than 5 articles in a section, that's fine — note it in the output. If a section is empty, the topic is too narrow; tell the user and suggest broadening.

### Phase 3 — Generate structured summaries

Read `$WORKDIR/brief.json` and write one structured summary per article into `$WORKDIR/summaries.json`. Use the article's `full_text` when present (for open-access PMC articles); otherwise summarize from `abstract`.

Each summary is a JSON object with four fields, each ~50 words (~200 words total):

- `background`: Why this study was done. The clinical question or gap.
- `methods`: Study design, sample size, key measurements, comparators.
- `results`: The actual findings with numbers when reported.
- `clinical_takeaway`: What this means for practice. Be direct — say whether the evidence supports a change in practice, is preliminary, or contradicts prior work. Do not hedge with "more research is needed" unless the authors specifically conclude that.

Also write a `synthesis` field: a single 80–120 word paragraph at the top of the JSON that synthesizes the 10 articles into a unified take. What's the consensus? What's contested? What's emerging? Write it as if briefing a busy clinician colleague — direct, no fluff.

The summaries JSON structure:

```json
{
  "synthesis": "...",
  "recent": {
    "12345678": {"background": "...", "methods": "...", "results": "...", "clinical_takeaway": "..."},
    "23456789": {...}
  },
  "cited": {
    "34567890": {...}
  }
}
```

Keys under `recent` and `cited` are the PMIDs from the brief JSON.

**Quality bar:** Do not paraphrase the abstract back at me. Extract the substantive content. If an abstract is uninformative (e.g., a conference proceedings stub), say so in the takeaway field rather than padding.

### Phase 4 — Build the PDF

Pick an output location the user can find. On macOS default to `~/Downloads/` (always visible in Finder). In sandbox/Claude.ai environments where outputs go through a specific path, use that instead:

```bash
# Default: macOS Downloads folder
OUTDIR="$HOME/Downloads"
# Sandbox override: if /mnt/user-data/outputs exists, use it
[ -d "/mnt/user-data/outputs" ] && OUTDIR="/mnt/user-data/outputs"

python3 "$SKILL_DIR/scripts/build_pdf.py" "$WORKDIR/brief.json" \
  --summaries "$WORKDIR/summaries.json" \
  --out "$OUTDIR/literature-brief-<topic-slug>.pdf"
```

The PDF generator handles all formatting using a clean palette (teal #0F4C5C, bronze #B08D57, beige #F5EFE6). Article cards, links, page chrome are pre-styled — do not modify the script unless the user asks for a different visual identity.

Use a short, descriptive slug for the filename (e.g., `literature-brief-oral-microbiome-perio.pdf`).

After generating the PDF, tell the user the full path and what they're getting in one line: e.g., "10 articles, 5 recent + 5 most-cited, with PubMed/DOI/PMC links." Do not re-summarize the synthesis paragraph in chat — they'll read it in the PDF.

If `present_files` is available (sandbox/Claude.ai), call it with the PDF path. On a local Mac via Claude Desktop, just print the path so the user can `open` it from terminal.

## Edge cases

- **Email argument:** Both NCBI and Europe PMC require a contact email per their TOS. Default to `your-email@domain.com` (or whatever the user provides). NCBI/Europe PMC use this for rate limiting and contact, not authentication.
- **Rate limits:** The script sleeps between calls to respect NCBI's 3 req/s limit. If you hit a 429, wait 10 seconds and retry once.
- **Non-English articles:** PubMed indexes translated titles. Summarize in the language of the user's original request, regardless of the article's original language.
- **Preprints:** PubMed indexes some preprints (e.g., from medRxiv via NIH). If a result is flagged as a preprint, note it in the clinical_takeaway field so the user knows the evidence isn't peer-reviewed.
- **Topics with no results:** If both sections come back empty, the search query is wrong. Try a broader version once before reporting failure.
- **Network access:** The script needs outbound HTTPS to `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk`, and `api.crossref.org`. If the script returns HTTP 403, it's a network policy issue (corporate firewall or restricted sandbox), not a bug. On a normal home/office network including macOS this works without configuration.

## Customization the user might request

- **More articles per section:** Pass `--per-section N` to the search script. The PDF generator handles any count.
- **Different time window for "recent":** Edit the `current_year - 3` line in `search_articles.py` `build_brief()` function.
- **Different visual identity:** The palette constants are at the top of `build_pdf.py`. Swap hex codes there.
- **Bilingual output (Spanish + English):** Generate two summary objects and run `build_pdf.py` twice with different output names.
