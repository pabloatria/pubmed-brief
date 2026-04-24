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
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, KeepTogether,
    HRFlowable, Table, TableStyle, PageBreak,
)


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
SAFE_URL_RE = re.compile(r"^https://(pubmed\.ncbi\.nlm\.nih\.gov|"
                         r"doi\.org|www\.ncbi\.nlm\.nih\.gov)/[^\s<>\"']+$")


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
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=22, leading=26, textColor=TEAL, spaceAfter=4, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=11, leading=14, textColor=BRONZE, spaceAfter=10, alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=15, leading=18, textColor=WHITE, alignment=TA_LEFT,
            backColor=TEAL, borderPadding=(8, 10, 8, 10), spaceBefore=8, spaceAfter=14,
        ),
        "synthesis_label": ParagraphStyle(
            "synthesis_label", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=BRONZE, spaceAfter=4,
        ),
        "synthesis": ParagraphStyle(
            "synthesis", parent=base["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=CHARCOAL, alignment=TA_JUSTIFY, spaceAfter=14,
        ),
        "art_title": ParagraphStyle(
            "art_title", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=TEAL, spaceAfter=3,
        ),
        "art_meta": ParagraphStyle(
            "art_meta", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=9, leading=11, textColor=GRAY, spaceAfter=6,
        ),
        "art_section_label": ParagraphStyle(
            "art_section_label", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=BRONZE, spaceAfter=2,
        ),
        "art_body": ParagraphStyle(
            "art_body", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=13, textColor=CHARCOAL, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "links": ParagraphStyle(
            "links", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=12, textColor=TEAL, spaceAfter=4,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName="Helvetica",
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
    canv.setFont("Helvetica", 8)
    canv.setFillColor(TEAL)
    text_x = LETTER[0] / 2
    credit_y = 0.28 * inch
    canv.drawCentredString(text_x, credit_y, AUTHOR_CREDIT_TEXT)

    # Make the credit line clickable — link rect spans the full text width
    text_width = canv.stringWidth(AUTHOR_CREDIT_TEXT, "Helvetica", 8)
    canv.linkURL(
        AUTHOR_INSTAGRAM_URL,
        (text_x - text_width / 2, credit_y - 1, text_x + text_width / 2, credit_y + 8),
        relative=0,
        thickness=0,
    )

    # Page number on a second line
    canv.setFillColor(GRAY)
    canv.drawCentredString(text_x, 0.14 * inch, f"Page {doc.page}")
    canv.restoreState()


# ---------- Helpers ----------
def format_authors(authors: list[str], max_shown: int = 3) -> str:
    if not authors:
        return "Authors not listed"
    if len(authors) <= max_shown:
        return ", ".join(authors)
    return ", ".join(authors[:max_shown]) + ", et al."


def article_block(article: dict, idx: int, summary: dict, styles: dict) -> list:
    """Build one article card as a flowable group."""
    flowables = []

    # Title with index — escape title since it comes from PubMed
    title_text = f"<b>{idx}.</b> {safe(article.get('title', ''))}"
    flowables.append(Paragraph(title_text, styles["art_title"]))

    # Meta line: authors • journal • year • citations (all escaped)
    meta_parts = [safe(format_authors(article.get("authors", [])))]
    if article.get("journal"):
        meta_parts.append(safe(article["journal"]))
    if article.get("year"):
        meta_parts.append(safe(article["year"]))
    if article.get("citations"):
        meta_parts.append(f"Cited by {int(article['citations'])}")
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


def cover_block(brief: dict, synthesis: str, styles: dict) -> list:
    flowables = []
    flowables.append(Spacer(1, 0.15 * inch))
    flowables.append(Paragraph("Literature Brief", styles["title"]))
    flowables.append(Paragraph(
        f"Query: <b>{safe(brief.get('query', ''))}</b>", styles["subtitle"]
    ))
    try:
        gen_dt = datetime.fromisoformat(brief["generated_at"]).strftime("%B %d, %Y")
    except (KeyError, ValueError):
        gen_dt = "Unknown date"
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
    story.extend(cover_block(brief, summaries.get("synthesis", ""), styles))

    # Section 1: Most Recent
    recent_blocks = [Paragraph("Most Recent (last 3 years)", styles["section"])]
    for i, article in enumerate(brief["recent"], 1):
        summary = summaries.get("recent", {}).get(article["pmid"], {})
        recent_blocks.append(KeepTogether(article_block(article, i, summary, styles)))
    # Keep section header glued to first article
    if len(recent_blocks) >= 2:
        story.append(KeepTogether(recent_blocks[:2]))
        story.extend(recent_blocks[2:])
    else:
        story.extend(recent_blocks)

    # Section 2: Most Cited
    story.append(Spacer(1, 0.1 * inch))
    cited_blocks = [Paragraph("Most Cited (all-time)", styles["section"])]
    for i, article in enumerate(brief["cited"], 1):
        summary = summaries.get("cited", {}).get(article["pmid"], {})
        cited_blocks.append(KeepTogether(article_block(article, i, summary, styles)))
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
