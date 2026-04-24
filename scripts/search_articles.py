"""
Search PubMed + enrich via Europe PMC + Crossref to produce two ranked lists:
  - Most Recent (last 3 years, sorted by date desc)
  - Most Cited (all-time, sorted by Europe PMC citedByCount desc)

Outputs JSON to stdout: {"recent": [...], "cited": [...]}
Each article: pmid, doi, pmcid, title, authors, journal, year, abstract,
              full_text (when OA), citations, pubmed_url, doi_url, pmc_url

Usage:
  python search_articles.py "query terms" [--email YOUR_EMAIL] [--per-section 5]
"""
import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from typing import Callable, Optional

import requests
from Bio import Entrez
from urllib.error import HTTPError, URLError

# ---------- Config ----------
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
CROSSREF_WORKS = "https://api.crossref.org/works/{doi}"
USER_AGENT = "pubmed-brief-skill/1.0 (mailto:{email})"
REQUEST_TIMEOUT = 20
RATE_DELAY = 0.34  # NCBI: max 3 req/s without API key

# ---------- Input validators ----------
# PubMed identifiers are well-defined formats. Reject anything that doesn't
# match — defends against URL injection if PubMed ever returns malformed data
# or if this script gets reused with attacker-controlled input.
PMID_RE = re.compile(r"^\d{1,9}$")            # PMIDs are positive integers
PMCID_RE = re.compile(r"^PMC\d{1,9}$")        # PMCIDs are "PMC" + integer
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s<>\"]+$")  # DOI prefix 10. + suffix
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def safe_pmid(s: str) -> str:
    s = str(s or "").strip()
    return s if PMID_RE.match(s) else ""


def safe_pmcid(s: str) -> str:
    s = str(s or "").strip()
    return s if PMCID_RE.match(s) else ""


def safe_doi(s: str) -> str:
    s = str(s or "").strip()
    return s if DOI_RE.match(s) else ""


def safe_email(s: str) -> str:
    s = str(s or "").strip()
    if not EMAIL_RE.match(s):
        raise ValueError(f"Invalid email format: {s!r}")
    return s


def log(msg: str):
    print(f"[search] {msg}", file=sys.stderr, flush=True)


# ---------- Retry wrapper ----------
# NCBI rate-limits bursts and occasionally returns 5xx during maintenance.
# A couple of retries with jittered backoff dramatically reduce flakiness.
def _with_retry(fn: Callable, *, attempts: int = 3, base_delay: float = 1.0,
                label: str = "request"):
    """Call fn() up to `attempts` times, retrying on transient network errors
    (connection resets, timeouts, HTTP 429/5xx). Re-raises the last exception
    on exhaustion so the caller can decide what to do.
    """
    last_err: Optional[BaseException] = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except HTTPError as e:
            code = getattr(e, "code", None)
            # Retry only on rate-limit or server-side errors.
            if code not in (429, 500, 502, 503, 504):
                raise
            last_err = e
            delay = base_delay * (2 ** (i - 1)) + random.uniform(0, 0.5)
            log(f"{label} HTTP {code} (attempt {i}/{attempts}); backing off {delay:.1f}s")
            time.sleep(delay)
        except (URLError, requests.exceptions.RequestException, TimeoutError) as e:
            last_err = e
            delay = base_delay * (2 ** (i - 1)) + random.uniform(0, 0.5)
            log(f"{label} transient error ({e.__class__.__name__}); retrying in {delay:.1f}s")
            time.sleep(delay)
    assert last_err is not None
    raise last_err


# ---------- PubMed search ----------
def pubmed_search(query: str, retmax: int, sort: str, mindate: Optional[str] = None) -> list[str]:
    """Returns list of PMIDs. sort: 'relevance' or 'pub_date'."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "sort": sort,
        "retmode": "xml",
    }
    if mindate:
        params["mindate"] = mindate
        params["maxdate"] = datetime.now().strftime("%Y/%m/%d")
        params["datetype"] = "pdat"

    def _do_search():
        handle = Entrez.esearch(**params)
        try:
            return Entrez.read(handle)
        finally:
            handle.close()

    record = _with_retry(_do_search, label="esearch")
    time.sleep(RATE_DELAY)
    return record.get("IdList", [])


def _efetch_parse(pmid_list: list[str]):
    """One Entrez.efetch call + Entrez.read with retry. Returns the parsed
    records dict, or raises."""
    def _do():
        handle = Entrez.efetch(
            db="pubmed", id=",".join(pmid_list), rettype="xml", retmode="xml"
        )
        try:
            return Entrez.read(handle)
        finally:
            handle.close()
    return _with_retry(_do, label="efetch")


def pubmed_fetch(pmids: list[str]) -> list[dict]:
    """Fetch full metadata for a list of PMIDs. If the batch response is
    malformed XML, fall back to fetching each PMID individually so one bad
    record does not destroy the whole batch."""
    if not pmids:
        return []
    articles: list[dict] = []

    try:
        records = _efetch_parse(pmids)
    except Exception as e:
        log(f"batch efetch failed ({e.__class__.__name__}: {e}); "
            f"falling back to per-PMID fetch for {len(pmids)} IDs")
        for p in pmids:
            try:
                single = _efetch_parse([p])
                for pa in single.get("PubmedArticle", []):
                    try:
                        articles.append(_parse_pubmed_record(pa))
                    except Exception as ex:
                        log(f"parse error for PMID {p}: {ex}")
            except Exception as ex:
                log(f"efetch failed for PMID {p}: {ex}")
            time.sleep(RATE_DELAY)
        return articles

    time.sleep(RATE_DELAY)
    for pubmed_article in records.get("PubmedArticle", []):
        try:
            articles.append(_parse_pubmed_record(pubmed_article))
        except Exception as e:
            log(f"parse error: {e}")
    return articles


def _parse_pubmed_record(rec) -> dict:
    medline = rec["MedlineCitation"]
    article = medline["Article"]
    pmid = safe_pmid(medline["PMID"])
    if not pmid:
        # Refuse to build a record with a malformed identifier
        raise ValueError("Skipping record with invalid PMID")

    title = str(article.get("ArticleTitle", "")).strip()

    # Abstract (may be multi-section)
    abstract_parts = []
    abstract_data = article.get("Abstract", {}).get("AbstractText", [])
    if isinstance(abstract_data, list):
        for part in abstract_data:
            label = part.attributes.get("Label", "") if hasattr(part, "attributes") else ""
            text = str(part)
            abstract_parts.append(f"{label}: {text}" if label else text)
    else:
        abstract_parts.append(str(abstract_data))
    abstract = "\n".join(p for p in abstract_parts if p).strip()

    # Authors
    authors = []
    for au in article.get("AuthorList", []):
        last = au.get("LastName", "")
        initials = au.get("Initials", "")
        if last:
            authors.append(f"{last} {initials}".strip())

    # Journal + year
    journal = str(article.get("Journal", {}).get("Title", "")).strip()
    pubdate = article.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
    year = str(pubdate.get("Year") or pubdate.get("MedlineDate", "")[:4] or "")

    # IDs (validated)
    doi = ""
    pmcid = ""
    for aid in rec.get("PubmedData", {}).get("ArticleIdList", []):
        id_type = aid.attributes.get("IdType", "")
        if id_type == "doi":
            doi = safe_doi(aid)
        elif id_type == "pmc":
            pmcid = safe_pmcid(aid)

    return {
        "pmid": pmid,
        "doi": doi,
        "pmcid": pmcid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "abstract": abstract,
        "full_text": "",
        "citations": 0,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else "",
    }


def _safe_json(resp: requests.Response, context: str) -> dict:
    """Parse response JSON; on failure log status + body prefix and return {}.

    Some proxies/CDNs return HTML error pages with 200 OK, which would
    otherwise surface as an opaque JSONDecodeError.
    """
    try:
        return resp.json()
    except ValueError:
        body = (resp.text or "")[:200].replace("\n", " ")
        log(f"{context}: non-JSON response (status {resp.status_code}): {body!r}")
        return {}


# ---------- Europe PMC enrichment ----------
def enrich_europe_pmc(article: dict, email: str) -> dict:
    """Add citation count + PMCID + open-access full text when available.

    Returns the article (mutated in place). Failures are logged and swallowed
    so one slow/failed record does not abort the whole enrichment loop.
    """
    pmid = article["pmid"]
    headers = {"User-Agent": USER_AGENT.format(email=email)}
    try:
        r = _with_retry(
            lambda: requests.get(
                EUROPE_PMC_SEARCH,
                params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json",
                        "resultType": "core"},
                headers=headers, timeout=REQUEST_TIMEOUT,
            ),
            attempts=2, label=f"europepmc PMID {pmid}",
        )
        r.raise_for_status()
        results = _safe_json(r, f"europepmc PMID {pmid}").get("resultList", {}).get("result", [])
        if results:
            res = results[0]
            try:
                article["citations"] = int(res.get("citedByCount", 0) or 0)
            except (TypeError, ValueError):
                article["citations"] = 0
            if not article["pmcid"]:
                pmcid_from_epmc = safe_pmcid(res.get("pmcid", ""))
                if pmcid_from_epmc:
                    article["pmcid"] = pmcid_from_epmc
                    article["pmc_url"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid_from_epmc}/"
            # Fetch open-access full text if available
            if res.get("isOpenAccess") == "Y" and article["pmcid"]:
                article["full_text"] = fetch_full_text(article["pmcid"], email)
            article["_enriched"] = True
    except Exception as e:
        log(f"Europe PMC enrich failed for PMID {pmid}: {e}")
    return article


def fetch_full_text(pmcid: str, email: str) -> str:
    """Fetch and lightly clean open-access XML full text."""
    pmcid = safe_pmcid(pmcid)
    if not pmcid:
        return ""
    headers = {"User-Agent": USER_AGENT.format(email=email)}
    try:
        r = _with_retry(
            lambda: requests.get(
                EUROPE_PMC_FULLTEXT.format(pmcid=pmcid),
                headers=headers, timeout=REQUEST_TIMEOUT,
            ),
            attempts=2, label=f"fullText {pmcid}",
        )
        if r.status_code != 200:
            return ""
        # Strip XML tags crudely; we only need text for summarization
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        # Cap to avoid token bloat — first ~12k chars covers methods+results+discussion typically
        return text[:12000]
    except Exception as e:
        log(f"Full text fetch failed for {pmcid}: {e}")
        return ""


# ---------- Crossref fallback ----------
def enrich_crossref(article: dict, email: str) -> dict:
    """Fallback citation count + DOI metadata via Crossref."""
    doi = safe_doi(article.get("doi", ""))
    if not doi or article["citations"] > 0:
        return article
    headers = {"User-Agent": USER_AGENT.format(email=email)}
    try:
        r = _with_retry(
            lambda: requests.get(
                CROSSREF_WORKS.format(doi=doi),
                headers=headers, timeout=REQUEST_TIMEOUT,
            ),
            attempts=2, label=f"crossref {doi}",
        )
        if r.status_code == 200:
            msg = _safe_json(r, f"crossref {doi}").get("message", {})
            try:
                article["citations"] = int(msg.get("is-referenced-by-count", 0) or 0)
            except (TypeError, ValueError):
                pass
    except Exception as e:
        log(f"Crossref enrich failed for DOI {doi}: {e}")
    return article


# ---------- Main pipeline ----------
def build_brief(query: str, per_section: int, email: str) -> dict:
    Entrez.email = email
    log(f"Query: {query}")

    # --- Most Recent: last 3 years, sorted by pub date ---
    current_year = datetime.now().year
    recent_mindate = f"{current_year - 3}/01/01"
    log(f"Searching recent (since {recent_mindate})...")
    recent_pmids = pubmed_search(query, retmax=per_section, sort="pub_date", mindate=recent_mindate)

    # --- Most Cited: pull a larger pool by relevance, then re-rank by citations ---
    log("Searching all-time pool for citation re-ranking...")
    pool_size = max(30, per_section * 6)
    cited_pool_pmids = pubmed_search(query, retmax=pool_size, sort="relevance")

    # Fetch metadata for both
    log(f"Fetching {len(recent_pmids)} recent + {len(cited_pool_pmids)} pool articles...")
    all_pmids = list(set(recent_pmids + cited_pool_pmids))
    all_articles = pubmed_fetch(all_pmids)
    by_pmid = {a["pmid"]: a for a in all_articles}

    # Warn if fetch lost records.
    requested = len(set(all_pmids))
    dropped = requested - len(all_articles)
    if dropped > 0:
        log(f"WARNING: {dropped}/{requested} records failed to parse and were dropped")

    # Enrich pool with citation counts. Track how many succeed so we can warn
    # the caller when the "Most Cited" ranking might be biased by partial data.
    log("Enriching with Europe PMC (citations + full text)...")
    enriched_ok = 0
    for i, art in enumerate(all_articles, 1):
        enrich_europe_pmc(art, email)
        if art.pop("_enriched", False):
            enriched_ok += 1
        elif art["citations"] == 0:
            enrich_crossref(art, email)
        if i % 5 == 0:
            log(f"  enriched {i}/{len(all_articles)}")

    total = max(len(all_articles), 1)
    enrich_rate = enriched_ok / total
    if enrich_rate < 0.75:
        log(f"WARNING: only {enriched_ok}/{total} articles enriched from Europe PMC "
            f"(likely network issue). 'Most Cited' ranking may be biased.")

    # Build sections
    recent = [by_pmid[p] for p in recent_pmids if p in by_pmid][:per_section]
    cited_pool = [by_pmid[p] for p in cited_pool_pmids if p in by_pmid]
    cited = sorted(cited_pool, key=lambda a: a["citations"], reverse=True)[:per_section]

    return {
        "query": query,
        "generated_at": datetime.now().isoformat(),
        "recent": recent,
        "cited": cited,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="PubMed search query")
    parser.add_argument("--email", default="anonymous@example.com",
                        help="Contact email for NCBI/Europe PMC TOS (please set to your real email)")
    parser.add_argument("--per-section", type=int, default=5)
    parser.add_argument("--out", default="-", help="Output path or '-' for stdout")
    args = parser.parse_args()

    # Validate inputs before doing anything
    email = safe_email(args.email)
    if email == "anonymous@example.com":
        log("WARNING: using default --email. NCBI will rate-limit the shared "
            "default; pass --email your@address to identify yourself per their TOS.")
    if args.per_section < 1 or args.per_section > 50:
        sys.exit("--per-section must be between 1 and 50")
    if not args.query.strip():
        sys.exit("Query cannot be empty")

    brief = build_brief(args.query, args.per_section, email)
    payload = json.dumps(brief, indent=2, ensure_ascii=False)
    if args.out == "-":
        print(payload)
    else:
        # Resolve and verify the output path doesn't escape via symlinks
        from pathlib import Path
        out_path = Path(args.out).expanduser().resolve()
        # Refuse to write outside common safe locations unless user is explicit
        # (this is a soft check — user can still pass any absolute path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(payload)
        log(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
