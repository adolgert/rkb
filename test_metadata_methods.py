"""Test all metadata extraction methods against data/initial/ PDFs.

Methods tested:
1. PDF embedded metadata (pymupdf doc.metadata + XMP)
2. DOI extraction (improved regex) -> CrossRef API
3. arXiv ID extraction (from XMP, filename, text) -> arXiv Client API
4. Semantic Scholar search (by title from first page)
5. GROBID header extraction
"""

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import arxiv
import pymupdf
import requests

PDF_DIR = Path("data/initial")


# ---------------------------------------------------------------------------
# 1. PDF embedded metadata (standard + XMP)
# ---------------------------------------------------------------------------
DC_NS = "http://purl.org/dc/elements/1.1/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _parse_xmp(xmp_xml: str) -> dict:
    """Extract Dublin Core fields from XMP metadata XML."""
    result: dict = {}
    try:
        root = ET.fromstring(xmp_xml)
    except ET.ParseError:
        return result

    # Title: dc:title -> rdf:Alt -> rdf:li
    for alt in root.iter(f"{{{DC_NS}}}title"):
        for li in alt.iter(f"{{{RDF_NS}}}li"):
            if li.text and li.text.strip():
                result["title"] = li.text.strip()
                break

    # Authors: dc:creator -> rdf:Seq -> rdf:li
    authors = []
    for seq in root.iter(f"{{{DC_NS}}}creator"):
        for li in seq.iter(f"{{{RDF_NS}}}li"):
            if li.text and li.text.strip():
                authors.append(li.text.strip())
    if authors:
        result["authors"] = authors

    # Identifier: dc:identifier (arXiv URL, DOI, etc.)
    for desc in root.iter(f"{{{RDF_NS}}}Description"):
        ident = desc.get(f"{{{DC_NS}}}identifier")
        if ident:
            result["identifier"] = ident
    # Also check element form
    for el in root.iter(f"{{{DC_NS}}}identifier"):
        if el.text and el.text.strip():
            result["identifier"] = el.text.strip()

    # Subject/categories: dc:subject -> rdf:Seq -> rdf:li
    subjects = []
    for seq in root.iter(f"{{{DC_NS}}}subject"):
        for li in seq.iter(f"{{{RDF_NS}}}li"):
            if li.text and li.text.strip():
                subjects.append(li.text.strip())
    if subjects:
        result["subjects"] = subjects

    # Publisher
    for desc in root.iter(f"{{{RDF_NS}}}Description"):
        pub = desc.get(f"{{{DC_NS}}}publisher")
        if pub:
            result["publisher"] = pub

    return result


def extract_embedded_metadata(pdf_path: Path) -> dict | None:
    try:
        doc = pymupdf.open(pdf_path)
        meta = doc.metadata
        # Try XMP metadata
        xmp_data = {}
        try:
            xmp_xml = doc.get_xml_metadata()
            if xmp_xml:
                xmp_data = _parse_xmp(xmp_xml)
        except Exception:
            pass
        doc.close()

        # Prefer XMP title over standard metadata title
        title = xmp_data.get("title")
        if not title:
            title = meta.get("title", "").strip() if meta.get("title") else None

        # Prefer XMP authors (structured list) over flat author string
        authors = xmp_data.get("authors")
        author_str = meta.get("author", "").strip() if meta.get("author") else None

        # Filter out garbage titles (too short, or generic)
        if title and len(title) < 3:
            title = None

        return {
            "title": title,
            "author": author_str,
            "authors": authors,
            "identifier": xmp_data.get("identifier"),
            "subjects": xmp_data.get("subjects"),
            "publisher": xmp_data.get("publisher"),
            "method": "embedded",
        }
    except Exception as e:
        return {"error": str(e), "method": "embedded"}


# ---------------------------------------------------------------------------
# 2. Improved DOI extraction -> CrossRef
# ---------------------------------------------------------------------------
DOI_PATTERN = re.compile(
    r"(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)"  # optional prefix
    r"(10\.\d{4,}/[^\s,;)\]\"'}>]+)",              # the DOI itself
    re.IGNORECASE,
)
DOI_BARE = re.compile(r"\b(10\.\d{4,}/[^\s,;)\]\"'}>]+)")


def extract_doi(pdf_path: Path) -> str | None:
    try:
        doc = pymupdf.open(pdf_path)
        text = ""
        for i in range(min(3, len(doc))):
            text += doc[i].get_text()
        doc.close()
    except Exception:
        return None

    # Try prefixed DOI first (more reliable)
    m = DOI_PATTERN.search(text)
    if m:
        return m.group(1).rstrip(".,;)")
    # Fallback to bare DOI
    m = DOI_BARE.search(text)
    if m:
        return m.group(1).rstrip(".,;)")
    return None


def crossref_lookup(doi: str) -> dict | None:
    try:
        url = f"https://api.crossref.org/works/{doi}"
        resp = requests.get(url, headers={"User-Agent": "kbase-metadata-test/1.0"}, timeout=10)
        if resp.status_code != 200:
            return None
        msg = resp.json().get("message", {})
        title = msg["title"][0] if msg.get("title") else None
        authors = []
        for a in msg.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            authors.append(f"{given} {family}".strip() if given else family)
        year = None
        for key in ("published", "published-print", "published-online"):
            if key in msg:
                parts = msg[key].get("date-parts", [[]])[0]
                if parts:
                    year = parts[0]
                    break
        abstract = msg.get("abstract")
        return {
            "title": title, "authors": authors, "year": year,
            "journal": (msg.get("container-title") or [None])[0],
            "abstract": abstract[:120] + "..." if abstract and len(abstract) > 120 else abstract,
            "method": "doi_crossref",
        }
    except Exception as e:
        return {"error": str(e), "method": "doi_crossref"}


# ---------------------------------------------------------------------------
# 3. arXiv ID extraction -> arXiv Client API
# ---------------------------------------------------------------------------
ARXIV_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_OLD_PATTERN = re.compile(r"arXiv:([a-z-]+/\d{7})", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", re.IGNORECASE)

arxiv_client = arxiv.Client(
    page_size=1,
    delay_seconds=3.0,
    num_retries=3,
)


def extract_arxiv_id(pdf_path: Path, xmp_identifier: str | None = None) -> str | None:
    # 1. Try XMP dc:identifier (e.g. "https://arxiv.org/abs/2505.23302v1")
    if xmp_identifier:
        m = ARXIV_URL_PATTERN.search(xmp_identifier)
        if m:
            return m.group(1)
        m = ARXIV_PATTERN.search(xmp_identifier)
        if m:
            return m.group(1)

    # 2. Try filename
    fname = pdf_path.stem
    m = ARXIV_PATTERN.search(fname)
    if m:
        return m.group(1)
    m = ARXIV_OLD_PATTERN.search(fname)
    if m:
        return m.group(1)

    # 3. Try first page text
    try:
        doc = pymupdf.open(pdf_path)
        text = doc[0].get_text() if len(doc) > 0 else ""
        doc.close()
    except Exception:
        return None

    m = ARXIV_PATTERN.search(text)
    if m:
        return m.group(1)
    m = ARXIV_OLD_PATTERN.search(text)
    if m:
        return m.group(1)
    return None


def arxiv_lookup(arxiv_id: str) -> dict | None:
    try:
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(arxiv_client.results(search))
        if not results:
            return None
        result = results[0]
        abstract = result.summary.strip().replace("\n", " ") if result.summary else None
        if abstract and len(abstract) > 120:
            abstract = abstract[:120] + "..."
        return {
            "title": result.title,
            "authors": [a.name for a in result.authors],
            "year": result.published.year if result.published else None,
            "abstract": abstract,
            "categories": result.categories,
            "method": "arxiv",
        }
    except Exception as e:
        return {"error": str(e), "method": "arxiv"}


# ---------------------------------------------------------------------------
# 4. Semantic Scholar search (by title from first page)
# ---------------------------------------------------------------------------
def get_first_page_title(pdf_path: Path) -> str | None:
    """Extract candidate title from first page text."""
    try:
        doc = pymupdf.open(pdf_path)
        if not doc:
            return None
        text = doc[0].get_text()
        doc.close()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return None
        # Use first non-trivial line as candidate title
        for line in lines[:5]:
            if len(line) > 10:
                return line[:200]
        return lines[0][:200] if lines else None
    except Exception:
        return None


def semantic_scholar_search(title: str, max_retries: int = 3) -> dict | None:
    for attempt in range(max_retries):
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": title[:200],
                "limit": 1,
                "fields": "title,authors,year,abstract,venue,externalIds",
            }
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"    [S2 rate limited, waiting {wait}s...]")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                return None
            data = resp.json()
            papers = data.get("data", [])
            if not papers:
                return None
            paper = papers[0]
            abstract = paper.get("abstract")
            if abstract and len(abstract) > 120:
                abstract = abstract[:120] + "..."
            return {
                "title": paper.get("title"),
                "authors": [a["name"] for a in paper.get("authors", []) if a.get("name")],
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "abstract": abstract,
                "s2_ids": paper.get("externalIds"),
                "method": "semantic_scholar",
            }
        except Exception as e:
            return {"error": str(e), "method": "semantic_scholar"}
    return {"error": "rate limited after retries", "method": "semantic_scholar"}


# ---------------------------------------------------------------------------
# 5. GROBID header extraction
# ---------------------------------------------------------------------------
def grobid_extract(pdf_path: Path) -> dict | None:
    try:
        with pdf_path.open("rb") as f:
            resp = requests.post(
                "http://localhost:8070/api/processHeaderDocument",
                files={"input": f},
                headers={"Accept": "application/xml"},
                timeout=60,
            )
        if resp.status_code != 200:
            return {"error": f"status {resp.status_code}", "method": "grobid"}

        root = ET.fromstring(resp.text)
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}

        title_el = root.find(".//tei:titleStmt/tei:title", ns)
        title = title_el.text if title_el is not None and title_el.text else None

        authors = []
        for author in root.findall(".//tei:sourceDesc//tei:author", ns):
            forename = author.find(".//tei:forename", ns)
            surname = author.find(".//tei:surname", ns)
            if surname is not None and surname.text:
                parts = []
                if forename is not None and forename.text:
                    parts.append(forename.text)
                parts.append(surname.text)
                authors.append(" ".join(parts))

        year = None
        date_el = root.find(".//tei:publicationStmt//tei:date", ns)
        if date_el is not None:
            when = date_el.get("when", "")
            if len(when) >= 4:
                try:
                    year = int(when[:4])
                except ValueError:
                    pass

        journal = None
        j_el = root.find(".//tei:monogr/tei:title[@level='j']", ns)
        if j_el is not None and j_el.text:
            journal = j_el.text

        # Try to get abstract
        abstract = None
        abs_el = root.find(".//tei:profileDesc/tei:abstract", ns)
        if abs_el is not None:
            # Get all text content
            abs_text = "".join(abs_el.itertext()).strip()
            if abs_text:
                abstract = abs_text[:120] + "..." if len(abs_text) > 120 else abs_text

        return {
            "title": title, "authors": authors, "year": year,
            "journal": journal, "abstract": abstract, "method": "grobid",
        }
    except Exception as e:
        return {"error": str(e), "method": "grobid"}


# ---------------------------------------------------------------------------
# Main: run all methods on all PDFs
# ---------------------------------------------------------------------------
def has_title(result: dict | None) -> bool:
    return result is not None and result.get("title") is not None and "error" not in result


def has_abstract(result: dict | None) -> bool:
    return result is not None and result.get("abstract") is not None and "error" not in result


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"Testing {len(pdfs)} PDFs\n")

    methods = ["embedded", "doi_crossref", "arxiv", "semantic_scholar", "grobid"]
    title_counts = {m: 0 for m in methods}
    abstract_counts = {m: 0 for m in methods}
    any_title = 0
    any_abstract = 0
    total = len(pdfs)

    for i, pdf in enumerate(pdfs):
        print(f"[{i+1}/{total}] {pdf.name}")

        results = {}

        # 1. Embedded
        results["embedded"] = extract_embedded_metadata(pdf)

        # 2. DOI -> CrossRef
        doi = extract_doi(pdf)
        if doi:
            cr = crossref_lookup(doi)
            if cr is not None:
                cr["doi"] = doi
            results["doi_crossref"] = cr
        else:
            results["doi_crossref"] = None

        # 3. arXiv (use XMP identifier if available)
        xmp_identifier = None
        embedded = results.get("embedded")
        if embedded and not embedded.get("error"):
            xmp_identifier = embedded.get("identifier")
        arxiv_id = extract_arxiv_id(pdf, xmp_identifier)
        if arxiv_id:
            results["arxiv"] = arxiv_lookup(arxiv_id)
        else:
            results["arxiv"] = None

        # 4. Semantic Scholar (use best available title, or first page)
        candidate_title = None
        for m in ["doi_crossref", "arxiv", "embedded"]:
            r = results.get(m)
            if r and r.get("title"):
                candidate_title = r["title"]
                break
        if not candidate_title:
            candidate_title = get_first_page_title(pdf)
        if candidate_title:
            results["semantic_scholar"] = semantic_scholar_search(candidate_title)
            time.sleep(1.5)  # Rate limit for S2
        else:
            results["semantic_scholar"] = None

        # 5. GROBID
        results["grobid"] = grobid_extract(pdf)

        # Print results
        got_any_title = False
        got_any_abstract = False
        for method in methods:
            r = results[method]
            ht = has_title(r)
            ha = has_abstract(r)
            if ht:
                title_counts[method] += 1
                got_any_title = True
            if ha:
                abstract_counts[method] += 1
                got_any_abstract = True

            if r is None:
                print(f"  {method:20s}  --")
            elif "error" in r:
                print(f"  {method:20s}  ERROR: {r['error'][:80]}")
            else:
                t = (r.get("title") or "?")[:70]
                y = r.get("year", "?")
                a = "abs" if ha else "   "
                extra = ""
                if method == "embedded" and r.get("identifier"):
                    extra = f"  id={r['identifier'][:50]}"
                if method == "arxiv" and r.get("categories"):
                    extra = f"  cats={r['categories']}"
                print(f"  {method:20s}  [{a}] {y} | {t}{extra}")

        if got_any_title:
            any_title += 1
        if got_any_abstract:
            any_abstract += 1
        print()

    # Summary
    print("=" * 72)
    print(f"{'METHOD':20s}  {'TITLE':>8s}  {'ABSTRACT':>8s}  {'RATE':>6s}")
    print("-" * 72)
    for m in methods:
        rate = f"{title_counts[m]/total*100:.0f}%"
        print(f"{m:20s}  {title_counts[m]:>5d}/{total:<3d} {abstract_counts[m]:>5d}/{total:<3d} {rate:>6s}")
    print("-" * 72)
    print(f"{'ANY method':20s}  {any_title:>5d}/{total:<3d} {any_abstract:>5d}/{total:<3d} {any_title/total*100:.0f}%")


if __name__ == "__main__":
    main()
