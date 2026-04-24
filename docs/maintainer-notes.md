# Maintainer notes

This file is for the repo owner (currently Pablo Atria). It documents the
workflow for keeping the two distribution paths (Claude skill + ChatGPT
Custom GPT) in sync. A user installing either version does **not** need to
read this — they should read the top-level [README](../README.md) and, if
they're self-hosting their own GPT, [`chatgpt/SETUP.md`](../chatgpt/SETUP.md).

## After publishing a new version of the ChatGPT Custom GPT

1. Publish per [`chatgpt/SETUP.md` Step 5](../chatgpt/SETUP.md#step-5--optional-publish-to-the-gpt-store).
2. Copy the assigned `https://chatgpt.com/g/g-<hash>-pubmed-brief` URL.
3. Edit the main [README.md](../README.md) — replace the current URL in the
   "Try in ChatGPT" badge, the 👉 callout, and the Install → ChatGPT section.
4. Commit as `docs: update published PubMed Brief Custom GPT URL`.

**Current live URL:** <https://chatgpt.com/g/g-69ebe5ed75408191a5055cc67d3c6c88-pubmed-brief>

## After a change to `scripts/build_pdf.py` or the bundled fonts

The Claude path auto-updates via `git pull`. The Custom GPT does not — you
have to re-upload.

1. In ChatGPT → **My GPTs** → PubMed Brief → **Configure**.
2. Scroll to **Knowledge**, delete the old `build_pdf.py` (and any affected
   `.ttf` files), upload the new ones from the repo.
3. If you changed [`chatgpt/CUSTOM_GPT_INSTRUCTIONS.md`](../chatgpt/CUSTOM_GPT_INSTRUCTIONS.md),
   re-paste its contents into the **Instructions** field.
4. If you changed [`chatgpt/openapi.yaml`](../chatgpt/openapi.yaml), re-paste
   into **Actions → Schema**.
5. Save. No bump to the GPT Store listing is needed — the URL stays stable.

## Promoting both versions

When you send someone to this skill, match their platform:

- **Claude users** → `https://github.com/pabloatria/pubmed-brief` (README has
  the Claude install path at the top).
- **ChatGPT users** → the published GPT Store URL (zero-install for them).

Same input, same PDF output, same brand. Audience on Claude gets richer
citation/full-text data; audience on ChatGPT gets a zero-install experience.

## Things that don't change per version (useful to remember)

- `scripts/build_pdf.py` is the single source of truth for PDF layout. Never
  copy it into `chatgpt/`. The ChatGPT setup tells users to upload *this*
  file, not a fork.
- The DejaVu fonts in `scripts/fonts/` are public domain. Bundling is fine.
- `scripts/search_articles.py` is Claude-only. The OpenAPI schema in
  `chatgpt/openapi.yaml` is the ChatGPT analogue.
