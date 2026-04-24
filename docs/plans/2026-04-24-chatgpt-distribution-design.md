# Cross-platform distribution: add ChatGPT Custom GPT support

**Date:** 2026-04-24
**Status:** Approved
**Author:** Pablo Atria (with Claude Code)

## Problem

The `pubmed-brief` skill currently targets Claude only. A parallel ChatGPT
Custom GPT exists as unpublished drafts in `~/Downloads/Pubmed Skill/GPT/`
but is not in the GitHub repo, already drifts from the canonical
`build_pdf.py`, and duplicates code that will fork further with every fix.
Users who ask "does this work with ChatGPT?" have no documented path.

## Goals

- Single source of truth for `build_pdf.py` and the bundled fonts — used by
  both Claude (installed skill) and ChatGPT (Knowledge upload).
- Clear, short documentation explaining the two install paths. Users on
  either platform should find their route in under a minute from the README.
- Zero cost to maintainer. No hosted services, no API keys.
- Custom GPT published in the public GPT Store so it is discoverable.

## Non-goals

- Not building a Cloudflare Worker to proxy Europe PMC citation counts to
  ChatGPT. The existing GPT instructions already document this tradeoff;
  estimated citation counts remain acceptable.
- Not supporting full-text XML fetch in the ChatGPT flow. Abstracts-only
  summaries are acceptable for the ChatGPT path; Claude keeps the richer
  Europe PMC full-text pipeline.
- Not auto-syncing the Custom GPT's Knowledge files when the repo updates
  (ChatGPT has no API for this). A manual re-upload is documented instead.

## Design

### Repository layout

```
pubmed-brief/
├── README.md                    (gains "Install" section with two platforms)
├── chatgpt/
│   ├── SETUP.md                 (step-by-step Custom GPT setup)
│   ├── CUSTOM_GPT_INSTRUCTIONS.md
│   └── openapi.yaml
├── scripts/
│   ├── build_pdf.py             (shared — ChatGPT uploads this file)
│   ├── search_articles.py       (Claude-only; NCBI is handled by the
│   │                             OpenAPI action in ChatGPT)
│   └── fonts/                   (shared — ChatGPT uploads these too)
│       ├── DejaVuSans.ttf
│       ├── DejaVuSans-Bold.ttf
│       ├── DejaVuSans-Oblique.ttf
│       ├── DejaVuSans-BoldOblique.ttf
│       └── LICENSE
```

No duplicated Python code. ChatGPT users download `scripts/build_pdf.py`
and the four `.ttf` files once and re-upload to the GPT's Knowledge when
upstream changes.

### Font path resolution (the only code change)

ChatGPT's Custom GPT Knowledge upload is **flat** — every file lands in
`/mnt/data/` with no subdirectory structure. The current loader expects
`./fonts/DejaVuSans.ttf` relative to the script.

Fix: probe two locations, prefer the subfolder, fall back to the flat
layout, then gracefully degrade to Helvetica if neither is found.

```python
_FONT_DIR_PRIMARY = Path(__file__).resolve().parent / "fonts"
_FONT_DIR_FALLBACK = Path(__file__).resolve().parent  # flat (ChatGPT)

def _font_path(name: str) -> Optional[Path]:
    for d in (_FONT_DIR_PRIMARY, _FONT_DIR_FALLBACK):
        p = d / name
        if p.exists():
            return p
    return None
```

Existing stress tests (15-case format_authors + pathological build) still
pass. One new test: rename `fonts/` to simulate the flat layout, copy the
TTFs next to `build_pdf.py`, confirm the PDF still renders with DejaVu.

### ChatGPT artifacts (rewrites of the `~/Downloads/.../GPT/` drafts)

**`chatgpt/SETUP.md`** — Step-by-step: create the Custom GPT, upload
`build_pdf.py` + 4 `.ttf` files to Knowledge, paste the OpenAPI schema,
test, and publish to the GPT Store. Includes the known tradeoffs vs the
Claude version in a single table.

**`chatgpt/CUSTOM_GPT_INSTRUCTIONS.md`** — Cleaned-up version of the
existing draft. Key fixes: use `generated_at` (matches build_pdf.py) not
`generated_on`; use the new `pmc.ncbi.nlm.nih.gov` URL format; instruct
the GPT to emit `authors` as `list[str]` (the format builder prefers);
reference the bundled fonts explicitly so the GPT knows to call the
script with the correct working directory.

**`chatgpt/openapi.yaml`** — The OpenAPI 3.1 spec for NCBI eutils wrappers
(esearch, esummary, efetch). No change from the existing draft; it's
already validated and working.

### README "Install" section

Replaces the current single-platform install block with a two-path choice
near the top of the README:

```markdown
## Install

Pick your AI:

### Claude
[Current one-line install instructions]

### ChatGPT
See [`chatgpt/SETUP.md`](./chatgpt/SETUP.md). ~10-minute setup, requires
ChatGPT Plus. Or use the hosted Custom GPT directly:
https://chat.openai.com/g/g-XXXXX-pubmed-brief

Same PDF output on both. Same articles. Same brand.
```

The hosted GPT URL placeholder gets filled in after the user publishes the
GPT to the store.

### Documented tradeoffs (ChatGPT vs. Claude)

Kept in `chatgpt/SETUP.md` in a single table:

| Feature                         | Claude           | ChatGPT                                  |
|---------------------------------|------------------|------------------------------------------|
| Auto-trigger from any chat      | ✅                | ⚠️ Only inside the Custom GPT             |
| True citation counts            | ✅ (Europe PMC)   | ❌ Estimated from article age + journal   |
| PMC full-text fetch             | ✅                | ⚠️ Abstract-only summaries                |
| Install steps                   | 1 line           | ~10 minutes in ChatGPT UI                 |
| Cost                            | Free (with subscription) | Requires ChatGPT Plus              |
| PDF visual identity             | Identical        | Identical                                 |

## Implementation order

1. Patch `scripts/build_pdf.py` font loader — one small change, full test.
2. Create `chatgpt/` with the three rewritten artifacts.
3. Update README with the two-path Install section and repo-structure
   listing.
4. Verify: flat-layout font test; end-to-end PDF from the pathological
   fixture; live NCBI query still works.
5. Commit as one clean unit, push. User publishes the GPT and pastes the
   store URL back; second tiny commit fills in the README link.

## Risks / open questions

- **Stale Knowledge uploads.** If the user updates `build_pdf.py` in the
  repo but forgets to re-upload to the Custom GPT, ChatGPT users will run
  an old version. `SETUP.md` has a "Maintenance" section that makes this
  explicit.
- **OpenAPI parser strictness.** ChatGPT sometimes rejects schemas that
  pass other validators. Verified the existing draft was accepted by the
  user in an earlier session, so the risk is low, but we'll re-verify
  after any whitespace changes.
- **GPT Store review.** Public publication goes through OpenAI's review.
  Typical turnaround is minutes to hours; the user does this outside the
  repo workflow.
