"""MCP server exposing the RKB knowledge base via the Model Context Protocol.

Run with::

    uv run python rkb/mcp_server.py

Or via fastmcp dev mode::

    fastmcp dev rkb/mcp_server.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastmcp import FastMCP

from rkb.api import KnowledgeBase
from rkb.collection.canonical_store import canonical_dir
from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig
from rkb.core.chunk_store import ChunkStore

LOGGER = logging.getLogger("rkb.mcp_server")

# ---------------------------------------------------------------------------
# Return-type dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """A single document result returned from the knowledge base.

    Attributes:
        doc_id: Stable unique identifier (SHA-256 of PDF content).
        score: Higher score means more relevant.
        title: Paper title or, if unknown, name of source PDF.
        dir_path: Path to directory containing the PDF, Markdown, and images.
        chunk_cnt: Number of Markdown chunks indexed for search.
        page_cnt: Number of pages in the PDF. May be None.
        abstract: Abstract text. May be empty if not extracted.
    """

    doc_id: str
    score: float
    title: str
    dir_path: str
    chunk_cnt: int | None
    page_cnt: int | None
    abstract: str


@dataclass
class Chunk:
    """A section of text from a document.

    Attributes:
        doc_id: Unique identifier of the document.
        chunk_idx: Index of this chunk within the document.
        chunk_cnt: Total number of chunks in this document.
        content: The text that makes up this chunk.
        similarity: Relevance score in [0, 1]. Higher is better. None when
            reading sequentially rather than by relevance.
    """

    doc_id: str
    chunk_idx: int
    chunk_cnt: int
    content: str
    similarity: float | None


@dataclass
class DocumentInfo:
    """Full metadata for a single document in the knowledge base.

    Attributes:
        doc_id: Stable unique identifier (SHA-256 of PDF content).
        title: Title extracted from the document. Empty string if unknown.
        authors: Author names. Empty list if unknown.
        year: Publication year. None if unknown.
        journal: Journal or venue name. None if unknown.
        abstract: Abstract text. Empty string if not extracted.
        page_cnt: Number of pages in the PDF. None if unavailable.
        chunk_cnt: Number of Markdown chunks indexed for search.
        dir_path: Path to the canonical directory with PDF, Markdown, and images.
    """

    doc_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    abstract: str = ""
    page_cnt: int | None = None
    chunk_cnt: int = 0
    dir_path: str = ""


# ---------------------------------------------------------------------------
# Server initialisation — single instances shared across all tool calls
# ---------------------------------------------------------------------------

mcp = FastMCP("RKB Knowledge Base")

_config = CollectionConfig.load(None)
_sha256_dir = _config.library_root / "sha256"
_kb = KnowledgeBase(
    db_path=_sha256_dir / "rkb_chroma_db",
    registry_path=_sha256_dir / "rkb_documents.db",
)
_catalog = Catalog(_config.catalog_db)
_catalog.initialize()
_chunks = ChunkStore(_sha256_dir / "rkb_chunks.db")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _resolved_meta(doc_id: str) -> dict:
    """Return resolved metadata dict, defaulting to empty dict if absent."""
    meta = _catalog.get_resolved_metadata(doc_id)
    return meta if meta is not None else {}


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_knowledge_base(query: str, mode: str, max_results: int) -> list[SearchHit]:
    """Retrieve documents that match a query.

    Args:
        query: A natural language query or specific phrase, depending on mode.
        mode: One of "hybrid", "semantic", or "bm25". Semantic uses vector
            similarity. BM25 matches keywords. Hybrid combines both.
        max_results: Maximum number of documents to return.

    Returns:
        List of matching documents sorted by relevance, highest first.
    """
    api_hits = _kb.search(query, n=max_results, mode=mode)
    results: list[SearchHit] = []
    for hit in api_hits:
        doc_id = hit.doc_id
        catalog_row = _catalog.get_canonical_file(doc_id)
        meta = _resolved_meta(doc_id)

        page_cnt: int | None = None
        if catalog_row is not None:
            page_cnt = catalog_row.get("page_count")

        dir_path = str(canonical_dir(_config.library_root, doc_id))

        title = meta.get("title") or hit.title or ""
        abstract = meta.get("abstract") or ""

        # Chunk count: ChunkStore is the authoritative source.
        chunk_cnt_int: int | None = _chunks.get_chunk_count(doc_id) or None

        results.append(
            SearchHit(
                doc_id=doc_id,
                score=hit.score,
                title=title,
                dir_path=dir_path,
                chunk_cnt=chunk_cnt_int,
                page_cnt=page_cnt,
                abstract=abstract,
            )
        )
    return results


@mcp.tool()
def read_document(doc_id: str, chunk_start: int, chunk_finish: int) -> list[Chunk]:
    """Retrieve sequential chunks of Markdown from a document.

    Returns the Markdown version of the document, preferring the marker
    extraction over nougat where both exist.

    Args:
        doc_id: The stable unique identifier (SHA-256) for the document.
        chunk_start: 0-based index of the first chunk to return.
        chunk_finish: 0-based index of the last chunk to return (inclusive).
            The maximum valid value is chunk_cnt - 1.

    Returns:
        List of Chunk objects in index order. Empty if the document is not
        found or the range is out of bounds.
    """
    raw_chunks = _chunks.get_chunks(doc_id, chunk_start, chunk_finish)
    chunk_cnt = _chunks.get_chunk_count(doc_id)
    return [
        Chunk(
            doc_id=doc_id,
            chunk_idx=idx,
            chunk_cnt=chunk_cnt,
            content=content,
            similarity=None,
        )
        for idx, content in raw_chunks
    ]


@mcp.tool()
def search_within_document(doc_id: str, query: str, max_chunks: int) -> list[Chunk]:
    """Return chunks that match a query within a single document.

    Useful for navigating longer documents or finding specific sections.

    Args:
        doc_id: Unique identifier of the document.
        query: A natural language query.
        max_chunks: Maximum number of chunks to return.

    Returns:
        List of Chunk objects ranked by relevance, highest first.
    """
    result = _kb._search_service.search_by_document(  # noqa: SLF001
        query=query, doc_id=doc_id, n_results=max_chunks
    )
    chunk_cnt = _chunks.get_chunk_count(doc_id)
    chunks: list[Chunk] = []
    for cr in result.chunk_results:
        chunk_idx = cr.metadata.get("chunk_index", 0)
        chunks.append(
            Chunk(
                doc_id=cr.metadata.get("doc_id", doc_id),
                chunk_idx=chunk_idx,
                chunk_cnt=chunk_cnt,
                content=cr.content,
                similarity=cr.similarity,
            )
        )
    return chunks


@mcp.tool()
def get_document(doc_id: str) -> DocumentInfo:
    """Return full metadata for a single document.

    Args:
        doc_id: The stable unique identifier (SHA-256) for the document.

    Returns:
        DocumentInfo with all available metadata fields. Fields that could
        not be determined are None or empty.
    """
    catalog_row = _catalog.get_canonical_file(doc_id)
    meta = _resolved_meta(doc_id)

    title = meta.get("title") or ""
    if not title and catalog_row is not None:
        title = catalog_row.get("display_name", "")

    authors: list[str] = meta.get("authors") or []
    year: int | None = meta.get("year")
    journal: str | None = meta.get("journal")
    abstract: str = meta.get("abstract") or ""

    page_cnt: int | None = None
    if catalog_row is not None:
        page_cnt = catalog_row.get("page_count")

    chunk_cnt = _chunks.get_chunk_count(doc_id)
    dir_path = str(canonical_dir(_config.library_root, doc_id))

    return DocumentInfo(
        doc_id=doc_id,
        title=title,
        authors=authors,
        year=year,
        journal=journal,
        abstract=abstract,
        page_cnt=page_cnt,
        chunk_cnt=chunk_cnt,
        dir_path=dir_path,
    )


if __name__ == "__main__":
    mcp.run()
