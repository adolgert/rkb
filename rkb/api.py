"""Clean Python API for interacting with the RKB knowledge base.

Example usage::

    from rkb.api import KnowledgeBase

    kb = KnowledgeBase()
    hits = kb.search("stochastic simulation stability", n=5)
    for h in hits:
        print(h.score, h.title, h.section)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.services.bm25_index import BM25Index
from rkb.services.search_service import SearchService

_DEFAULT_DB_PATH = "rkb_chroma_db"
_DEFAULT_REGISTRY_PATH = "rkb_documents.db"


@dataclass
class SearchHit:
    """A single search result at document level.

    Attributes:
        doc_id: Unique document identifier.
        score: Retrieval score (higher is more relevant).
        title: Document title from the registry (empty string if unknown).
        file_path: Path to the source PDF/Markdown, or None.
        best_chunk: Text of the highest-scoring chunk for the query.
        section: Section heading of *best_chunk* if available, else None.
    """

    doc_id: str
    score: float
    title: str = ""
    file_path: Path | None = None
    best_chunk: str = ""
    section: str | None = None


class KnowledgeBase:
    """High-level interface to the RKB knowledge base.

    Wires together :class:`~rkb.services.search_service.SearchService`,
    :class:`~rkb.services.bm25_index.BM25Index`, and the document registry
    so callers do not have to manage individual services.

    Args:
        db_path: Path to the Chroma vector database directory.  Defaults to
            ``rkb_chroma_db``.
        embedder: Name of the embedder to use (``"specter2"``, ``"chroma"``,
            or ``"ollama"``).  Defaults to ``"specter2"``.
        registry_path: Path to the SQLite document registry.  Defaults to
            ``rkb_documents.db``.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        embedder: str = "specter2",
        registry_path: Path | str | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path else Path(_DEFAULT_DB_PATH)
        self._registry_path = (
            Path(registry_path) if registry_path else Path(_DEFAULT_REGISTRY_PATH)
        )
        self._embedder_name = embedder

        self._registry = DocumentRegistry(self._registry_path)

        # Load BM25 index if it exists on disk
        self._bm25 = BM25Index(self._db_path)
        self._bm25.load()

        self._search_service = SearchService(
            db_path=self._db_path,
            embedder_name=embedder,
            registry=self._registry,
            bm25_index=self._bm25,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self, query: str, n: int = 10, mode: str = "hybrid"
    ) -> list[SearchHit]:
        """Search the knowledge base and return document-level hits.

        Args:
            query: Free-text query.
            n: Maximum number of results to return.
            mode: Search mode — ``"hybrid"`` (BM25 + semantic, default),
                ``"semantic"``, or ``"bm25"``.

        Returns:
            List of :class:`SearchHit` objects sorted by score descending.
        """
        ranked_docs, all_chunks, _ = self._search_service.search_documents_ranked(
            query=query, n_docs=n, mode=mode
        )

        # Build a quick lookup: chunk_id → ChunkResult
        chunk_lookup = {c.chunk_id: c for c in all_chunks}

        hits: list[SearchHit] = []
        for doc_score in ranked_docs:
            doc = self._registry.get_document(doc_score.doc_id)

            # Best chunk for this document
            display_data = self._search_service.get_display_data(
                doc_score, all_chunks, strategy="top_chunk"
            )
            best_chunk_text: str = display_data.get("chunk_text") or ""
            best_chunk_id: str | None = display_data.get("chunk_id")

            # Section heading from chunk metadata
            section: str | None = None
            if best_chunk_id and best_chunk_id in chunk_lookup:
                hierarchy = chunk_lookup[best_chunk_id].metadata.get(
                    "section_hierarchy", []
                )
                if hierarchy:
                    section = hierarchy[0] if isinstance(hierarchy, list) else str(hierarchy)

            title = ""
            file_path: Path | None = None
            if doc is not None:
                title = doc.title or ""
                file_path = doc.source_path

            hits.append(
                SearchHit(
                    doc_id=doc_score.doc_id,
                    score=doc_score.score,
                    title=title,
                    file_path=file_path,
                    best_chunk=best_chunk_text,
                    section=section,
                )
            )

        return hits

    def get_chunks(self, doc_id: str, query: str, n: int = 5) -> list[str]:
        """Return the top *n* chunks from *doc_id* most relevant to *query*.

        Args:
            doc_id: Document identifier.
            query: Query to rank chunks against.
            n: Number of chunks to return.

        Returns:
            List of chunk text strings, best-first.
        """
        result = self._search_service.search_by_document(
            query=query, doc_id=doc_id, n_results=n
        )
        return [cr.content for cr in result.chunk_results]

    def get_path(self, doc_id: str) -> Path | None:
        """Return the source file path for a document.

        Args:
            doc_id: Document identifier.

        Returns:
            Path to the PDF/Markdown file, or None if not found.
        """
        doc = self._registry.get_document(doc_id)
        return doc.source_path if doc is not None else None

    def index_status(self) -> dict[str, object]:
        """Return a summary of the current index state.

        Returns:
            Dictionary with keys:

            - ``total_chunks`` (int): number of chunks in the vector DB.
            - ``bm25_built`` (bool): whether the BM25 index is loaded.
            - ``embedder`` (str): name of the configured embedder.
        """
        stats = self._search_service.get_database_stats()
        return {
            "total_chunks": stats.get("total_chunks", 0),
            "bm25_built": self._bm25.is_built(),
            "embedder": self._embedder_name,
        }
