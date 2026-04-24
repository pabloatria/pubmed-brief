"""
Generate a PDF brief from the JSON produced by search_articles.py.

Default visual identity (teal/bronze/beige) — edit palette constants to customize.
  - Teal (primary)    #0F4C5C
  - Bronze (accent)   #B08D57
  - Beige (background) #F5EFE6
  - Charcoal (text)   #2B2B2B

Usage:
  python build_pdf.py brief.json --summaries summaries.json --out brief.pdf
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, KeepTogether,
    HRFlowable, Table, TableStyle, PageBreak,
)


# ---------- Font registration ----------
# Bundle DejaVu Sans (public domain) so names like "Revilla-León", "Wójcik",
# and Greek letters (β, μ, α) that are ubiquitous in biomedical abstracts
# render correctly. ReportLab's built-in Helvetica is WinAnsi-only and drops
# most non-Latin characters to empty boxes.
_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_REGISTERED = False


def _register_bundled_fonts() -> str:
    """Register the bundled DejaVu family. Returns the body-font name.

    Falls back to Helvetica (with a warning) if the bundled fonts are missing —
    the PDF will still generate but non-ASCII characters may render as blanks.
    """
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return "Body"
    try:
        pdfmetrics.registerFont(TTFont("Body", str(_FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Italic", str(_FONT_DIR / "DejaVuSans-Oblique.ttf")))
        pdfmetrics.registerFont(TTFont("Body-BoldItalic", str(_FONT_DIR / "DejaVuSans-BoldOblique.ttf")))
        registerFontFamily("Body",
                           normal="Body", bold="Body-Bold",
                           italic="Body-Italic", boldItalic="Body-BoldItalic")
        _FONT_REGISTERED = True
        return "Body"
    except Exception as e:
        print(f"[pdf] WARNING: bundled fonts not found ({e}); falling back to "
              "Helvetica. Non-ASCII characters may not render. Reinstall the "
              "skill to restore the fonts/ directory.", file=sys.stderr)
        return "Helvetica"


# ---------- Safety helpers ----------
# ReportLab's Paragraph interprets a subset of XML/HTML markup. Any content
# coming from PubMed (titles, abstracts, summaries) MUST be escaped before
# being passed to Paragraph() — otherwise an article title containing "<i>"
# could either break parsing or inject unintended markup into the PDF.
def safe(text: str) -> str:
    """Escape XML special chars for safe inclusion in ReportLab Paragraph."""
    if text is None:
        return ""
    return xml_escape(str(text), {'"': "&quot;", "'": "&apos;"})


# Strict URL whitelist for any href we render — prevents javascript: or
# data: URIs even if upstream data is somehow malformed.
# NOTE: Do not loosen this regex to accept quotes or angle brackets — the
# link templating in article_block() embeds the URL in an href without a
# second escape pass, and relies on this regex to keep it safe.
SAFE_URL_RE = re.compile(r"^https://(pubmed\.ncbi\.nlm\.nih\.gov|"
                         r"doi\.org|www\.ncbi\.nlm\.nih\.gov|"
                         r"pmc\.ncbi\.nlm\.nih\.gov)/[^\s<>\"']+$")


def safe_url(url: str) -> str:
    """Return the URL only if it matches our trusted-source whitelist."""
    url = (url or "").strip()
    return url if SAFE_URL_RE.match(url) else ""


# ---------- Palette ----------
TEAL = colors.HexColor("#0F4C5C")
TEAL_LIGHT = colors.HexColor("#3A7484")
BRONZE = colors.HexColor("#B08D57")
BEIGE = colors.HexColor("#F5EFE6")
CHARCOAL = colors.HexColor("#2B2B2B")
GRAY = colors.HexColor("#6B6B6B")
WHITE = colors.white


# ---------- Styles ----------
def build_styles():
    body_font = _register_bundled_fonts()
    # When DejaVu is registered we use the full family; on fallback to
    # Helvetica we keep the built-in variants to preserve bold/italic looks.
    if body_font == "Body":
        fn_regular, fn_bold, fn_italic = "Body", "Body-Bold", "Body-Italic"
    else:
        fn_regular, fn_bold, fn_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName=fn_bold,
            fontSize=22, leading=26, textColor=TEAL, spaceAfter=4, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontName=fn_regular,
            fontSize=11, leading=14, textColor=BRONZE, spaceAfter=10, alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading1"], fontName=fn_bold,
            fontSize=15, leading=18, textColor=WHITE, alignment=TA_LEFT,
            backColor=TEAL, borderPadding=(8, 10, 8, 10), spaceBefore=8, spaceAfter=14,
        ),
        "synthesis_label": ParagraphStyle(
            "synthesis_label", parent=base["Normal"], fontName=fn_bold,
            fontSize=10, leading=12, textColor=BRONZE, spaceAfter=4,
        ),
        "synthesis": ParagraphStyle(
            "synthesis", parent=base["Normal"], fontName=fn_regular,
            fontSize=10.5, leading=14, textColor=CHARCOAL, alignment=TA_JUSTIFY, spaceAfter=14,
        ),
        "art_title": ParagraphStyle(
            "art_title", parent=base["Heading2"], fontName=fn_bold,
            fontSize=12, leading=15, textColor=TEAL, spaceAfter=3,
        ),
        "art_meta": ParagraphStyle(
            "art_meta", parent=base["Normal"], fontName=fn_italic,
            fontSize=9, leading=11, textColor=GRAY, spaceAfter=6,
        ),
        "art_section_label": ParagraphStyle(
            "art_section_label", parent=base["Normal"], fontName=fn_bold,
            fontSize=9.5, leading=12, textColor=BRONZE, spaceAfter=2,
        ),
        "art_body": ParagraphStyle(
            "art_body", parent=base["Normal"], fontName=fn_regular,
            fontSize=10, leading=13, textColor=CHARCOAL, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "links": ParagraphStyle(
            "links", parent=base["Normal"], fontName=fn_bold,
            fontSize=9, leading=12, textColor=TEAL, spaceAfter=4,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName=fn_regular,
            fontSize=8, leading=10, textColor=GRAY, alignment=TA_CENTER,
        ),
    }


# ---------- Page chrome ----------
# Author credit shown in the footer of every page.
# These constants are intentionally module-level so forks can edit one place.
AUTHOR_CREDIT_TEXT = "Creado por: Pablo Atria  •  @pabloatria"
AUTHOR_INSTAGRAM_URL = "https://instagram.com/pabloatria"


def draw_page_chrome(canv: canvas.Canvas, doc):
    canv.saveState()
    # Top bronze rule
    canv.setFillColor(BRONZE)
    canv.rect(0, LETTER[1] - 0.25 * inch, LETTER[0], 0.08 * inch, fill=1, stroke=0)
    # Footer rule
    canv.setFillColor(TEAL)
    canv.rect(0, 0.45 * inch, LETTER[0], 0.04 * inch, fill=1, stroke=0)

    # Two-line footer: credit on top, page number below
    footer_font = "Body" if "Body" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canv.setFont(footer_font, 8)
    canv.setFillColor(TEAL)
    text_x = LETTER[0] / 2
    credit_y = 0.28 * inch
    canv.drawCentredString(text_x, credit_y, AUTHOR_CREDIT_TEXT)

    # Make the credit line clickable — link rect spans the full text width
    text_width = canv.stringWidth(AUTHOR_CREDIT_TEXT, footer_font, 8)
    canv.linkURL(
        AUTHOR_INSTAGRAM_URL,
        (text_x - text_width / 2, credit_y - 1, text_x + text_width / 2, credit_y + 8),
        relative=0,
        thickness=0,
    )

    # Page number on a second line
    canv.setFillColor(GRAY)
    canv.setFont(footer_font, 8)
    canv.drawCentredString(text_x, 0.14 * inch, f"Page {doc.page}")
    canv.restoreState()


# ---------- Helpers ----------
def format_authors(authors, max_shown: int = 3) -> str:
    """Render an author line.

    Accepts the list[str] produced by search_articles.py, but also survives a
    hand-built brief.json that passes a pre-joined string or a list of dicts —
    both of which occur when an LLM reconstructs the JSON offline. Never
    iterates a string character-by-character.
    """
    if not authors:
        return "Authors not listed"

    # Normalize string input: split on commas or semicolons and drop any
    # trailing "et al." marker so max_shown can apply uniformly.
    if isinstance(authors, str):
        s = authors.strip()
        if not s:
            return "Authors not listed"
        parts = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
        parts = [p for p in parts if p.lower().rstrip(".") != "et al"]
        authors = parts or [s]

    # Normalize list input: accept list[str] OR list[dict] (e.g. {"name":"X"}
    # or {"LastName":"X","Initials":"Y"}). Coerce anything else to str.
    if isinstance(authors, list):
        normalized = []
        for a in authors:
            if a is None:
                continue
            if isinstance(a, str):
                s = a.strip()
            elif isinstance(a, dict):
                last = a.get("last") or a.get("LastName") or a.get("lastName") or ""
                initials = a.get("initials") or a.get("Initials") or a.get("FirstName") or ""
                s = (a.get("name") or f"{last} {initials}".strip() or "").strip()
            else:
                s = str(a).strip()
            # Drop empty entries and any "et al." tokens that snuck into the list.
            if s and s.lower().rstrip(".") != "et al":
                normalized.append(s)
        authors = normalized
    else:
        # Neither list nor string (e.g. a bare int or a dict top-level).
        return "Authors not listed"

    if not authors:
        return "Authors not listed"
    if len(authors) <= max_shown:
        return ", ".join(authors)
    return ", ".join(authors[:max_shown]) + ", et al."


def _coerce_citations(value) -> int:
    """Return citation count as int, or 0 for anything unparseable.

    Handles "12", "12.0", 12.0, "  7+", None, "N/A", etc. without crashing.
    """
    if value is None or value is False:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        # Last-ditch: extract leading digits from a string like "12+" or "~40"
        m = re.search(r"\d+", str(value))
        return int(m.group(0)) if m else 0
    except Exception:
        return 0


def article_block(article: dict, idx: int, summary: dict, styles: dict) -> list:
    """Build one article card as a flowable group."""
    flowables = []

    # Title with index — escape title since it comes from PubMed
    title_text = f"<b>{idx}.</b> {safe(article.get('title', ''))}"
    flowables.append(Paragraph(title_text, styles["art_title"]))

    # Meta line: authors • journal • year • citations (all escaped)
    meta_parts = [safe(format_authors(article.get("authors") or []))]
    if article.get("journal"):
        meta_parts.append(safe(article["journal"]))
    if article.get("year"):
        meta_parts.append(safe(article["year"]))
    citations = _coerce_citations(article.get("citations"))
    if citations > 0:
        meta_parts.append(f"Cited by {citations}")
    flowables.append(Paragraph(" &nbsp;•&nbsp; ".join(meta_parts), styles["art_meta"]))

    # Structured summary — escape summary content (LLM-generated, but still untrusted)
    for label_key, label_text in [
        ("background", "Background"),
        ("methods", "Methods"),
        ("results", "Results"),
        ("clinical_takeaway", "Clinical Takeaway"),
    ]:
        body = (summary.get(label_key) or "").strip()
        if body:
            flowables.append(Paragraph(label_text.upper(), styles["art_section_label"]))
            flowables.append(Paragraph(safe(body), styles["art_body"]))

    # Links row — only render hrefs that pass the URL whitelist
    link_parts = []
    pubmed_url = safe_url(article.get("pubmed_url", ""))
    doi_url = safe_url(article.get("doi_url", ""))
    pmc_url = safe_url(article.get("pmc_url", ""))
    if pubmed_url:
        link_parts.append(f'<a href="{pubmed_url}" color="#0F4C5C"><b>&rarr; PubMed</b></a>')
    if doi_url:
        link_parts.append(f'<a href="{doi_url}" color="#0F4C5C"><b>&rarr; DOI</b></a>')
    if pmc_url:
        link_parts.append(f'<a href="{pmc_url}" color="#0F4C5C"><b>&rarr; Free Full Text (PMC)</b></a>')
    if link_parts:
        flowables.append(Paragraph(" &nbsp; ".join(link_parts), styles["links"]))

    # Bronze divider
    flowables.append(Spacer(1, 4))
    flowables.append(HRFlowable(width="100%", thickness=0.5, color=BRONZE,
                                spaceBefore=2, spaceAfter=10))
    return flowables


def _format_generated_at(value) -> str:
    """Render generated_at as 'April 24, 2026', tolerating ISO strings, unix
    timestamps (int/float), or missing/malformed input."""
    if value is None or value == "":
        return "Unknown date"
    # ISO 8601 string (the normal path from search_articles.py)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%B %d, %Y")
        except ValueError:
            # Also accept a plain YYYY-MM-DD or an integer-as-string timestamp
            try:
                return datetime.fromtimestamp(float(value)).strftime("%B %d, %Y")
            except (ValueError, OSError):
                return "Unknown date"
    # Numeric unix timestamp
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value)).strftime("%B %d, %Y")
        except (ValueError, OSError, OverflowError):
            return "Unknown date"
    return "Unknown date"


def cover_block(brief: dict, synthesis: str, styles: dict) -> list:
    flowables = []
    flowables.append(Spacer(1, 0.15 * inch))
    flowables.append(Paragraph("Literature Brief", styles["title"]))
    flowables.append(Paragraph(
        f"Query: <b>{safe(brief.get('query', ''))}</b>", styles["subtitle"]
    ))
    gen_dt = _format_generated_at(brief.get("generated_at"))
    flowables.append(Paragraph(f"Generated {safe(gen_dt)}", styles["art_meta"]))
    flowables.append(HRFlowable(width="100%", thickness=1.2, color=BRONZE,
                                spaceBefore=4, spaceAfter=12))
    if synthesis:
        flowables.append(Paragraph("CROSS-ARTICLE SYNTHESIS", styles["synthesis_label"]))
        flowables.append(Paragraph(safe(synthesis), styles["synthesis"]))
    return flowables


# ---------- Main ----------
def build_pdf(brief_path: str, summaries_path: str, out_path: str):
    with open(brief_path, encoding="utf-8") as f:
        brief = json.load(f)
    with open(summaries_path, encoding="utf-8") as f:
        summaries = json.load(f)

    styles = build_styles()
    # PDF metadata title — strip control chars and limit length
    safe_title = re.sub(r"[\x00-\x1f\x7f]", "", str(brief.get("query", ""))[:200])
    doc = BaseDocTemplate(
        out_path, pagesize=LETTER,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.55 * inch, bottomMargin=0.7 * inch,
        title=f"Literature Brief: {safe_title}",
        author="pubmed-brief",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=draw_page_chrome)])

    story = []
    synth_text = summaries.get("synthesis", "") if isinstance(summaries, dict) else ""
    story.extend(cover_block(brief, synth_text, styles))

    def _section_blocks(section_key: str, heading: str) -> list:
        """Build a section, tolerating missing/malformed input shapes."""
        articles = brief.get(section_key) or []
        if not isinstance(articles, list):
            # Guard against a hand-built brief.json that put a dict here
            print(f"[pdf] WARNING: brief['{section_key}'] is not a list; skipping section.",
                  file=sys.stderr)
            return [Paragraph(heading, styles["section"])]
        sec_summaries = summaries.get(section_key, {}) if isinstance(summaries, dict) else {}
        if not isinstance(sec_summaries, dict):
            sec_summaries = {}
        blocks = [Paragraph(heading, styles["section"])]
        for i, article in enumerate(articles, 1):
            if not isinstance(article, dict):
                continue
            pmid_key = article.get("pmid") or ""
            summary = sec_summaries.get(pmid_key, {}) if pmid_key else {}
            if not isinstance(summary, dict):
                summary = {}
            blocks.append(KeepTogether(article_block(article, i, summary, styles)))
        return blocks

    # Section 1: Most Recent
    recent_blocks = _section_blocks("recent", "Most Recent (last 3 years)")
    if len(recent_blocks) >= 2:
        story.append(KeepTogether(recent_blocks[:2]))
        story.extend(recent_blocks[2:])
    else:
        story.extend(recent_blocks)

    # Section 2: Most Cited
    story.append(Spacer(1, 0.1 * inch))
    cited_blocks = _section_blocks("cited", "Most Cited (all-time)")
    if len(cited_blocks) >= 2:
        story.append(KeepTogether(cited_blocks[:2]))
        story.extend(cited_blocks[2:])
    else:
        story.extend(cited_blocks)

    doc.build(story)
    print(f"[pdf] wrote {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("brief", help="JSON from search_articles.py")
    parser.add_argument("--summaries", required=True, help="JSON with structured summaries")
    parser.add_argument("--out", required=True, help="Output PDF path")
    args = parser.parse_args()
    build_pdf(args.brief, args.summaries, args.out)


if __name__ == "__main__":
    main()
