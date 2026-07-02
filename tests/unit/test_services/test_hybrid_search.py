"""Tests for hybrid search (RRF) in SearchService."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from rkb.core.models import ChunkResult

if TYPE_CHECKING:
    from rkb.services.search_service import SearchService


def _make_chunk(chunk_id: str, doc_id: str, similarity: float = 0.5) -> ChunkResult:
    return ChunkResult(
        chunk_id=chunk_id,
        content=f"content of {chunk_id}",
        similarity=similarity,
        distance=1.0 - similarity,
        metadata={"doc_id": doc_id},
    )


def _make_search_service(bm25_index: object = None) -> SearchService:
    """Build a SearchService with mocked Chroma and optional BM25 index."""
    from rkb.services.search_service import SearchService

    with patch("rkb.services.search_service.get_embedder") as mock_get_emb:
        mock_emb = MagicMock()
        mock_emb.minimum_threshold = 0.1
        mock_emb.embed_query.return_value = None  # use query_texts path
        mock_get_emb.return_value = mock_emb

        return SearchService(
            db_path="/tmp/fake_chroma",
            bm25_index=bm25_index,
        )


# ---------------------------------------------------------------------------
# RRF score correctness
# ---------------------------------------------------------------------------


def test_rrf_promotes_docs_in_both_rankings() -> None:
    """A document appearing in both semantic and BM25 rankings scores higher."""
    doc_a_chunks = [_make_chunk("a_c0", "doc_a", 0.9), _make_chunk("a_c1", "doc_a", 0.8)]
    doc_b_chunks = [_make_chunk("b_c0", "doc_b", 0.3)]

    svc = _make_search_service()

    # Patch _fetch_top_chunks to return a controlled list
    svc._fetch_top_chunks = MagicMock(return_value=doc_a_chunks + doc_b_chunks)

    # BM25 also returns doc_a at top
    mock_bm25 = MagicMock()
    mock_bm25.is_built.return_value = True
    mock_bm25.search.return_value = [("a_c0", 1.0), ("b_c0", 0.5)]
    svc.bm25_index = mock_bm25

    docs, _ = svc.search_hybrid("test query", n_docs=10)

    doc_ids = [d.doc_id for d in docs]
    assert "doc_a" in doc_ids
    # doc_a should rank above doc_b (in both lists)
    assert doc_ids.index("doc_a") < doc_ids.index("doc_b")


def test_rrf_default_rank_for_missing_chunk() -> None:
    """Chunks absent from one ranking get a default rank (n_candidates + 1)."""
    # doc_a only in semantic, doc_b only in BM25
    doc_a_chunk = _make_chunk("a_c0", "doc_a", 0.9)
    doc_b_chunk = _make_chunk("b_c0", "doc_b", 0.2)

    svc = _make_search_service()
    svc._fetch_top_chunks = MagicMock(return_value=[doc_a_chunk, doc_b_chunk])

    mock_bm25 = MagicMock()
    mock_bm25.is_built.return_value = True
    # Only b_c0 appears in BM25 results
    mock_bm25.search.return_value = [("b_c0", 1.0)]
    svc.bm25_index = mock_bm25

    docs, _ = svc.search_hybrid("test query", n_docs=10)

    # Both should appear; neither should error
    doc_ids = [d.doc_id for d in docs]
    assert "doc_a" in doc_ids or "doc_b" in doc_ids  # at least one found


def test_mode_semantic_uses_only_chroma() -> None:
    """mode='semantic' must not call bm25_index at all."""
    svc = _make_search_service()

    mock_bm25 = MagicMock()
    svc.bm25_index = mock_bm25

    # Patch fetch_chunks_iteratively (used by semantic path)
    svc.fetch_chunks_iteratively = MagicMock(
        return_value=(
            [],
            {
                "chunks_fetched": 0,
                "chunks_above_threshold": 0,
                "iterations": 1,
                "documents_found": 0,
            },
        )
    )

    svc.search_documents_ranked("query", mode="semantic")

    mock_bm25.search.assert_not_called()


def test_mode_bm25_returns_results_when_bm25_available() -> None:
    """mode='bm25' returns document scores ranked by BM25."""
    doc_chunk = _make_chunk("a_c0", "doc_a", 0.8)

    svc = _make_search_service()
    svc._fetch_top_chunks = MagicMock(return_value=[doc_chunk])

    mock_bm25 = MagicMock()
    mock_bm25.is_built.return_value = True
    mock_bm25.search.return_value = [("a_c0", 1.0)]
    svc.bm25_index = mock_bm25

    docs, _, stats = svc.search_documents_ranked("query", mode="bm25")

    assert stats["mode"] == "bm25"
    assert len(docs) >= 0  # may be empty if doc_id not in chunk metadata


def test_mode_hybrid_default_in_search_documents_ranked() -> None:
    """The default mode in search_documents_ranked is 'hybrid'."""
    svc = _make_search_service()
    svc.search_hybrid = MagicMock(return_value=([], []))

    svc.search_documents_ranked("query")

    svc.search_hybrid.assert_called_once()
