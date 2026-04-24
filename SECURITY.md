# Security Policy

## What this skill does (so you can decide if it's safe for your environment)

`pubmed-brief` makes outbound HTTPS requests to three public APIs:
- `eutils.ncbi.nlm.nih.gov` — PubMed search and metadata (NCBI E-utilities)
- `www.ebi.ac.uk` — Europe PMC for citation counts and open-access full text
- `api.crossref.org` — Crossref for fallback citation data

It writes one JSON file and one PDF file to paths you specify (default: `$TMPDIR` for JSON, `~/Downloads/` for PDF). It does not:

- Open any inbound network sockets
- Require or store credentials, API keys, or passwords
- Send telemetry, analytics, or usage data anywhere
- Execute shell commands, evaluate user input as code, or use unsafe deserialization (no `pickle`, no `eval`, no `subprocess`)
- Modify any system files or settings outside its working directory
- Request elevated privileges (no `sudo`)

The contact email you pass via `--email` is included in the User-Agent header for NCBI and Europe PMC requests, per their terms of service. It is not transmitted anywhere else.

## Threat model and mitigations

The skill processes data from external APIs (PubMed, Europe PMC, Crossref) and renders it into a PDF. The following defenses are in place:

| Risk | Mitigation |
|---|---|
| Malformed identifiers from API responses being injected into URLs | Strict regex validation of PMID, PMCID, DOI before use in any URL construction |
| Article titles/abstracts containing markup being interpreted by the PDF renderer | All external text is XML-escaped before passing to ReportLab `Paragraph()` |
| Malicious `javascript:` or `data:` URIs in clickable PDF links from API responses | URL whitelist limited to `pubmed.ncbi.nlm.nih.gov`, `doi.org`, and `www.ncbi.nlm.nih.gov` for all article hyperlinks |
| Path traversal via the `--out` argument | Output paths are resolved with `pathlib.Path.expanduser().resolve()` before opening |
| Email format validation | Regex check before being included in any HTTP request |
| Argument bounds | `--per-section` clamped to 1-50; empty queries rejected |

**Note on the footer credit link:** Every page footer contains a hardcoded clickable link to the author's Instagram profile (`https://instagram.com/pabloatria`). This is not user-controllable input — it's a constant in the source code. If you fork this skill, edit the `AUTHOR_CREDIT_TEXT` and `AUTHOR_INSTAGRAM_URL` constants near the top of `scripts/build_pdf.py` to change or remove it.

## Dependencies

The skill depends on three well-maintained Python packages:

- **biopython** (NCBI Entrez client; widely used in bioinformatics, ~50M+ downloads)
- **reportlab** (PDF generation; mature library, used in many production systems)
- **requests** (HTTP client; ubiquitous, audited)

It also bundles the **DejaVu Sans** font family (TTF files in `scripts/fonts/`), which is public domain. This is needed because ReportLab's built-in Helvetica is WinAnsi-only and silently drops non-ASCII characters common in biomedical abstracts (Greek letters, math symbols, author names like *Revilla-León* or *Wójcik*). DejaVu's own license permissions are included in `scripts/fonts/LICENSE`.

These are installed via `pip install` in `install.sh`. As of the last release of this skill, no known CVEs apply to these libraries (verified with `pip-audit`). You can re-verify at any time:

```bash
pip install pip-audit
pip-audit -r <(echo -e "biopython\nreportlab\nrequests")
```

## Reporting a vulnerability

If you discover a security issue in this skill, please report it privately by:

1. Opening a [GitHub Security Advisory](https://github.com/pabloatria/pubmed-brief/security/advisories/new) (preferred), or
2. Emailing the repository owner (see GitHub profile)

Please do not open a public issue for security-sensitive matters. Expected response time: within 7 days for acknowledgment.

## What you should still do as a user

This is open-source software, MIT licensed, with no warranty. Before installing on a sensitive system:

1. **Read the code.** It is small (~270 lines of Python plus a 60-line install script). You should be able to audit it in 15 minutes.
2. **Run it in a venv** if you don't trust your global Python environment:
   ```bash
   python3 -m venv ~/.pubmed-brief-venv
   source ~/.pubmed-brief-venv/bin/activate
   pip install biopython reportlab requests
   ```
3. **Don't run it on networks where outbound HTTPS to NCBI/EBI/Crossref is sensitive.** Some hospital and corporate networks restrict these by default. The skill respects those restrictions and will fail visibly with HTTP 403.
4. **Verify the PDF output before sharing.** This skill summarizes literature using an LLM in the workflow; treat output as a draft, not a citation-ready document. Verify all claims against the original papers (links are provided for exactly this reason).

## Out of scope

This skill is a research aid, not a clinical decision support tool. It is not regulated as medical software (does not meet FDA SaMD criteria), and its output should not be used as the sole basis for clinical decisions. Always cross-reference with primary literature.
