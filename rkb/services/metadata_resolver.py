"""Unified metadata resolver — runs extractors, caches, merges with Claude or rules."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import find_extraction_in_dir
from rkb.core.text_processing import title_candidate_from_marker_markdown, titles_match
from rkb.extractors.metadata.arxiv_extractor import ArxivExtractor
from rkb.extractors.metadata.doi_crossref import DOICrossRefExtractor
from rkb.extractors.metadata.grobid_extractor import GrobidExtractor
from rkb.extractors.metadata.semantic_scholar import SemanticScholarExtractor
from rkb.extractors.metadata.xmp import XMPExtractor
from rkb.extractors.metadata.zotero_translation import ZoteroTranslationExtractor

if TYPE_CHECKING:
    from pathlib import Path

    from rkb.collection.catalog import Catalog
    from rkb.extractors.metadata.models import DocumentMetadata

logger = logging.getLogger(__name__)

_TARGET_FIELDS = ("title", "authors", "year", "abstract")

# Title-page region of the Markdown used to corroborate title-search hits.
_TITLE_PAGE_CHARS = 4000

_PRIORITY_ORDER = [
    "zotero_translation",
    "grobid",
    "semantic_scholar",
    "doi_crossref",
    "arxiv",
    "xmp",
    "semantic_scholar_title",
    "crossref_title",
]

_CLAUDE_SYSTEM_PROMPT = """\
You are a metadata merging assistant. Given multiple metadata extractions for the \
same academic PDF, produce a single correct merged result.

Source reliability ranking (highest first): Zotero translation-server > GROBID > \
Semantic Scholar > CrossRef > arXiv > XMP > title-based searches (Semantic Scholar \
title / CrossRef title, least reliable because they are matched only by title text).

Rules:
- Prefer the highest-reliability source for each field.
- For authors, prefer the source with the most complete author list (full names over initials).
- For abstract, prefer the longest non-truncated version.
- Return ONLY valid JSON with keys: title, authors (list of strings), year (int or null), \
abstract (string or null), journal (string or null), doc_type (string or null).
"""


@dataclass
class ResolutionResult:
    """Result of resolving metadata for one document."""

    content_sha256: str
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    abstract: str | None = None
    journal: str | None = None
    doc_type: str | None = None
    resolution_method: str = "none"
    source_extractors: list[str] = field(default_factory=list)
    cached: bool = False


class MetadataResolver:
    """Orchestrate metadata extraction, caching, and merging."""

    def __init__(
        self,
        catalog: Catalog,
        *,
        anthropic_api_key: str | None = None,
        s2_api_key: str | None = None,
        grobid_url: str = "http://172.17.0.1:8070",
        translation_server_url: str | None = None,
        use_claude_merge: bool = True,
    ) -> None:
        self._catalog = catalog
        self._anthropic_api_key = anthropic_api_key
        self._grobid_url = grobid_url
        self._use_claude_merge = use_claude_merge and anthropic_api_key is not None

        self._xmp = XMPExtractor()
        self._grobid = GrobidExtractor(grobid_url=grobid_url)
        self._crossref = DOICrossRefExtractor()
        self._arxiv = ArxivExtractor()
        self._s2 = SemanticScholarExtractor(api_key=s2_api_key)
        self._translation = ZoteroTranslationExtractor(server_url=translation_server_url)

    def resolve(
        self, pdf_path: Path, content_sha256: str, *, force: bool = False
    ) -> ResolutionResult:
        """Check cache, run extractors, merge, store, return."""
        if not force:
            cached = self._catalog.get_resolved_metadata(content_sha256)
            if cached is not None:
                return ResolutionResult(
                    content_sha256=content_sha256,
                    title=cached.get("title"),
                    authors=cached.get("authors"),
                    year=cached.get("year"),
                    abstract=cached.get("abstract"),
                    journal=cached.get("journal"),
                    doc_type=cached.get("doc_type"),
                    resolution_method=cached.get("resolution_method", "cached"),
                    source_extractors=cached.get("source_extractors") or [],
                    cached=True,
                )

        sources = self._run_extractors(pdf_path, content_sha256)

        if not sources:
            return ResolutionResult(content_sha256=content_sha256)

        if self._use_claude_merge and len(sources) > 1:
            result = self._claude_merge(content_sha256, sources)
        else:
            result = self._rule_based_merge(content_sha256, sources)

        self._catalog.set_resolved_metadata(
            content_sha256,
            title=result.title,
            authors=result.authors,
            year=result.year,
            journal=result.journal,
            abstract=result.abstract,
            doc_type=result.doc_type,
            resolution_method=result.resolution_method,
            source_extractors=result.source_extractors,
        )

        return result

    def resolve_batch(
        self, items: list[tuple[Path, str]], *, force: bool = False
    ) -> list[ResolutionResult]:
        """Resolve metadata for a batch of (pdf_path, content_sha256) pairs."""
        return [self.resolve(path, sha, force=force) for path, sha in items]

    def _run_extractors(
        self, pdf_path: Path, content_sha256: str
    ) -> dict[str, DocumentMetadata]:
        """Run extractors in priority order, short-circuiting when possible."""
        sources: dict[str, DocumentMetadata] = {}
        doi: str | None = None
        arxiv_id: str | None = None

        doi, arxiv_id = self._extract_xmp(pdf_path, content_sha256, sources)
        if arxiv_id is None:
            arxiv_id = ArxivExtractor.id_from_filename(pdf_path.name)

        self._extract_translation(pdf_path, content_sha256, sources, doi, arxiv_id)
        self._extract_grobid(pdf_path, content_sha256, sources)
        self._extract_crossref(pdf_path, content_sha256, sources, doi)

        if self._all_fields_filled(sources):
            return sources

        self._extract_arxiv(content_sha256, sources, arxiv_id)

        if self._all_fields_filled(sources):
            return sources

        self._extract_s2(content_sha256, sources, doi)

        if self._best_field(sources, "title") is None:
            self._extract_title_search(pdf_path, content_sha256, sources)

        return sources

    def _extract_xmp(
        self, pdf_path: Path, content_sha256: str, sources: dict[str, DocumentMetadata]
    ) -> tuple[str | None, str | None]:
        """Run XMP extractor, return (doi, arxiv_id)."""
        try:
            xmp_result = self._xmp.extract_with_ids(pdf_path)
            if xmp_result.metadata.title:
                sources["xmp"] = xmp_result.metadata
                self._store_source(content_sha256, xmp_result.metadata)
            return xmp_result.doi, xmp_result.arxiv_id
        except Exception:
            logger.debug("XMP extraction failed for %s", pdf_path)
            return None, None

    def _extract_translation(
        self,
        pdf_path: Path,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        doi: str | None,
        arxiv_id: str | None,
    ) -> None:
        """Run Zotero translation-server extractor via known IDs or PDF text."""
        try:
            if doi:
                meta = self._translation.extract_by_identifier(doi)
            elif arxiv_id:
                meta = self._translation.extract_by_identifier(f"arXiv:{arxiv_id}")
            else:
                meta = self._translation.extract(pdf_path)
            if meta.title:
                sources["zotero_translation"] = meta
                self._store_source(content_sha256, meta)
        except Exception:
            logger.debug("Zotero translation-server extraction failed for %s", pdf_path)

    def _extract_grobid(
        self, pdf_path: Path, content_sha256: str, sources: dict[str, DocumentMetadata]
    ) -> None:
        """Run GROBID extractor."""
        try:
            grobid_meta = self._grobid.extract(pdf_path)
            if grobid_meta.title:
                sources["grobid"] = grobid_meta
                self._store_source(content_sha256, grobid_meta)
        except Exception:
            logger.debug("GROBID extraction failed for %s", pdf_path)

    def _extract_crossref(
        self,
        pdf_path: Path,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        doi: str | None,
    ) -> None:
        """Run CrossRef extractor via DOI or PDF text."""
        try:
            if doi:
                crossref_meta = self._crossref.query_crossref(doi)
            else:
                crossref_meta = self._crossref.extract(pdf_path)
            if crossref_meta.title:
                sources["doi_crossref"] = crossref_meta
                self._store_source(content_sha256, crossref_meta)
        except Exception:
            logger.debug("CrossRef extraction failed for %s", pdf_path)

    def _extract_arxiv(
        self,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        arxiv_id: str | None,
    ) -> None:
        """Run arXiv extractor if ID available."""
        if not arxiv_id:
            return
        try:
            arxiv_meta = self._arxiv.extract_by_id(arxiv_id)
            if arxiv_meta.title:
                sources["arxiv"] = arxiv_meta
                self._store_source(content_sha256, arxiv_meta)
        except Exception:
            logger.debug("arXiv lookup failed for %s", arxiv_id)

    def _extract_s2(
        self,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        doi: str | None,
    ) -> None:
        """Run Semantic Scholar extractor."""
        try:
            if doi:
                s2_meta = self._s2.extract_by_doi(doi)
            else:
                best_title = self._best_field(sources, "title")
                if not best_title:
                    return
                s2_meta = self._s2.extract_by_title(best_title)
            if s2_meta.title:
                sources["semantic_scholar"] = s2_meta
                self._store_source(content_sha256, s2_meta)
        except Exception:
            logger.debug("S2 extraction failed")

    def _extract_title_search(
        self, pdf_path: Path, content_sha256: str, sources: dict[str, DocumentMetadata]
    ) -> None:
        """Seed a bibliographic title search from the marker-pdf Markdown heading.

        Fires only when no identifier-based source produced a title (typically
        pre-DOI scans). Degrades silently when the Markdown is not present yet
        (e.g. enrich running before translate for a new file). A hit is accepted
        only when its title strongly matches the heading AND one of its authors
        appears in the title-page region of the Markdown — generic titles like
        "Markov Chain Monte Carlo Methods" match many unrelated works.
        """
        markdown = self._markdown_text(pdf_path)
        if not markdown:
            return
        candidate = title_candidate_from_marker_markdown(markdown)
        if not candidate:
            return
        title_page = markdown[:_TITLE_PAGE_CHARS]
        self._title_search_crossref(content_sha256, sources, candidate, title_page)
        self._title_search_s2(content_sha256, sources, candidate, title_page)

    def _markdown_text(self, pdf_path: Path) -> str | None:
        """Return the marker-pdf Markdown beside the PDF, if present."""
        try:
            markdown_path = find_extraction_in_dir(pdf_path.parent)
            if markdown_path is None:
                return None
            return markdown_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            return None

    @staticmethod
    def _author_on_title_page(meta: DocumentMetadata, title_page: str) -> bool:
        """Return True if an author family name appears in the title-page text."""
        if not meta.authors:
            return False
        haystack = title_page.casefold()
        for author in meta.authors:
            parts = author.split()
            family = parts[-1] if parts else ""
            if len(family) > 2 and family.casefold() in haystack:
                return True
        return False

    def _title_search_crossref(
        self,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        candidate: str,
        title_page: str,
    ) -> None:
        """Query CrossRef by title and store a validated, corroborated hit."""
        try:
            meta = self._crossref.search_by_title(candidate)
            if meta.title and self._author_on_title_page(meta, title_page):
                sources["crossref_title"] = meta
                self._store_source(content_sha256, meta)
        except Exception:
            logger.debug("CrossRef title search failed")

    def _title_search_s2(
        self,
        content_sha256: str,
        sources: dict[str, DocumentMetadata],
        candidate: str,
        title_page: str,
    ) -> None:
        """Query Semantic Scholar by title and store a validated, corroborated hit."""
        try:
            meta = self._s2.extract_by_title(candidate)
            if (
                meta.title
                and titles_match(candidate, meta.title)
                and self._author_on_title_page(meta, title_page)
            ):
                meta.extractor = "semantic_scholar_title"
                sources["semantic_scholar_title"] = meta
                self._store_source(content_sha256, meta)
        except Exception:
            logger.debug("S2 title search failed")

    def _store_source(self, content_sha256: str, meta: DocumentMetadata) -> None:
        """Cache one extractor result in the catalog."""
        self._catalog.add_metadata_source(
            content_sha256,
            meta.extractor,
            title=meta.title,
            authors=meta.authors,
            year=meta.year,
            journal=meta.journal,
            abstract=meta.abstract,
            raw_json=json.dumps(
                {
                    "title": meta.title,
                    "authors": meta.authors,
                    "year": meta.year,
                    "journal": meta.journal,
                    "abstract": meta.abstract,
                    "doc_type": meta.doc_type,
                }
            ),
        )

    @staticmethod
    def _all_fields_filled(sources: dict[str, DocumentMetadata]) -> bool:
        """Check if all target fields are covered by at least one source."""
        for fld in _TARGET_FIELDS:
            found = any(getattr(m, fld, None) is not None for m in sources.values())
            if not found:
                return False
        return True

    @staticmethod
    def _best_field(sources: dict[str, DocumentMetadata], field_name: str) -> str | None:
        """Return the first non-null value for a field in priority order."""
        for ext_name in _PRIORITY_ORDER:
            meta = sources.get(ext_name)
            if meta is not None:
                val = getattr(meta, field_name, None)
                if val is not None:
                    return val
        return None

    def _rule_based_merge(
        self, content_sha256: str, sources: dict[str, DocumentMetadata]
    ) -> ResolutionResult:
        """Merge by taking first non-null per field in priority order."""
        title = self._best_field(sources, "title")
        year = self._best_field(sources, "year")
        abstract = self._best_field(sources, "abstract")
        journal = self._best_field(sources, "journal")
        doc_type = self._best_field(sources, "doc_type")

        # For authors, prefer the longest list
        authors = None
        for ext_name in _PRIORITY_ORDER:
            meta = sources.get(ext_name)
            if (
                meta is not None
                and meta.authors
                and (authors is None or len(meta.authors) > len(authors))
            ):
                authors = meta.authors

        return ResolutionResult(
            content_sha256=content_sha256,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            journal=journal,
            doc_type=doc_type,
            resolution_method="rule_based",
            source_extractors=list(sources.keys()),
        )

    def _claude_merge(
        self, content_sha256: str, sources: dict[str, DocumentMetadata]
    ) -> ResolutionResult:
        """Use Claude Sonnet to merge conflicting metadata."""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._anthropic_api_key)

            sources_json = {}
            for ext_name, meta in sources.items():
                sources_json[ext_name] = {
                    "title": meta.title,
                    "authors": meta.authors,
                    "year": meta.year,
                    "abstract": meta.abstract,
                    "journal": meta.journal,
                    "doc_type": meta.doc_type,
                }

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                temperature=0,
                system=_CLAUDE_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Merge these metadata extractions into one correct result. "
                            "Return ONLY JSON.\n\n"
                            + json.dumps(sources_json, indent=2)
                        ),
                    }
                ],
            )

            raw_text = message.content[0].text
            logger.debug(
                "Claude merge raw response for %s:\n%s", content_sha256[:12], raw_text
            )

            response_text = raw_text.strip()
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                lines = [line for line in lines if not line.strip().startswith("```")]
                response_text = "\n".join(lines)
                logger.debug("Stripped code fences, parsing:\n%s", response_text)

            merged = json.loads(response_text)
            logger.debug("Claude merge parsed fields: %s", list(merged.keys()))

            return ResolutionResult(
                content_sha256=content_sha256,
                title=merged.get("title"),
                authors=merged.get("authors"),
                year=merged.get("year"),
                abstract=merged.get("abstract"),
                journal=merged.get("journal"),
                doc_type=merged.get("doc_type"),
                resolution_method="claude_merge",
                source_extractors=list(sources.keys()),
            )
        except Exception:
            logger.warning("Claude merge failed, falling back to rule-based merge", exc_info=True)
            return self._rule_based_merge(content_sha256, sources)
