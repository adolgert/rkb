"""Tests for rkb.api.KnowledgeBase."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.api import KnowledgeBase, SearchHit
from rkb.core.models import ChunkResult, DocumentScore, SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc_score(doc_id: str, score: float = 0.8) -> DocumentScore:
    return DocumentScore(doc_id=doc_id, score=score, metric_name="hybrid")


def _make_chunk(chunk_id: str, doc_id: str, content: str = "chunk text") -> ChunkResult:
    return ChunkResult(
        chunk_id=chunk_id,
        content=content,
        similarity=0.8,
        distance=0.2,
        metadata={"doc_id": doc_id},
    )


def _patch_kb(tmp_path: Path) -> KnowledgeBase:
    """Build a KnowledgeBase with all heavy dependencies mocked."""
    with (
        patch("rkb.api.DocumentRegistry"),
        patch("rkb.api.BM25Index") as mock_bm25_cls,
        patch("rkb.api.SearchService") as mock_ss_cls,
        patch("rkb.services.search_service.get_embedder"),
    ):
        mock_bm25_cls.return_value = MagicMock(is_built=MagicMock(return_value=False))
        mock_ss = MagicMock()
        mock_ss_cls.return_value = mock_ss

        kb = KnowledgeBase(db_path=tmp_path / "chroma", embedder="chroma")
        kb._search_service = mock_ss
        kb._bm25 = mock_bm25_cls.return_value

    return kb


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


def test_search_returns_search_hit_objects(tmp_path: Path) -> None:
    kb = _patch_kb(tmp_path)

    doc_score = _make_doc_score("doc_abc")
    chunk = _make_chunk("chunk_0", "doc_abc", "relevant text snippet")

    kb._search_service.search_documents_ranked.return_value = (
        [doc_score],
        [chunk],
        {},
    )
    kb._search_service.get_display_data.return_value = {
        "chunk_text": "relevant text snippet",
        "chunk_score": 0.8,
        "page_numbers": [1],
        "chunk_id": "chunk_0",
    }
    kb._registry.get_document.return_value = None

    hits = kb.search("test query", n=5, mode="hybrid")

    assert len(hits) == 1
    assert isinstance(hits[0], SearchHit)
    assert hits[0].doc_id == "doc_abc"
    assert hits[0].score == pytest.approx(0.8)
    assert hits[0].best_chunk == "relevant text snippet"


def test_search_populates_title_from_registry(tmp_path: Path) -> None:
    kb = _patch_kb(tmp_path)

    doc_score = _make_doc_score("doc_xyz")
    chunk = _make_chunk("chunk_0", "doc_xyz")

    kb._search_service.search_documents_ranked.return_value = ([doc_score], [chunk], {})
    kb._search_service.get_display_data.return_value = {
        "chunk_text": "",
        "chunk_id": "chunk_0",
    }

    mock_doc = MagicMock()
    mock_doc.title = "My Great Paper"
    mock_doc.source_path = Path("/papers/great_paper.pdf")
    kb._registry.get_document.return_value = mock_doc

    hits = kb.search("query")
    assert hits[0].title == "My Great Paper"
    assert hits[0].file_path == Path("/papers/great_paper.pdf")


def test_search_mode_routes_to_search_documents_ranked(tmp_path: Path) -> None:
    kb = _patch_kb(tmp_path)

    kb._search_service.search_documents_ranked.return_value = ([], [], {})

    kb.search("q", mode="semantic")
    call_kwargs = kb._search_service.search_documents_ranked.call_args.kwargs
    assert call_kwargs.get("mode") == "semantic"

    kb.search("q", mode="bm25")
    call_kwargs = kb._search_service.search_documents_ranked.call_args.kwargs
    assert call_kwargs.get("mode") == "bm25"


# ---------------------------------------------------------------------------
# get_chunks()
# ---------------------------------------------------------------------------


def test_get_chunks_delegates_to_search_by_document(tmp_path: Path) -> None:
    kb = _patch_kb(tmp_path)

    kb._search_service.search_by_document.return_value = SearchResult(
        query="test",
        chunk_results=[
            _make_chunk("c0", "doc1", "chunk A"),
            _make_chunk("c1", "doc1", "chunk B"),
        ],
    )

    chunks = kb.get_chunks("doc1", "my query", n=2)
    assert chunks == ["chunk A", "chunk B"]
    kb._search_service.search_by_document.assert_called_once_with(
        query="my query", doc_id="doc1", n_results=2
    )


# ---------------------------------------------------------------------------
# index_status()
# ---------------------------------------------------------------------------


def test_index_status_returns_expected_keys(tmp_path: Path) -> None:
    kb = _patch_kb(tmp_path)

    kb._search_service.get_database_stats.return_value = {"total_chunks": 42}
    kb._bm25.is_built.return_value = True
    kb._embedder_name = "specter2"

    status = kb.index_status()
    assert status["total_chunks"] == 42
    assert status["bm25_built"] is True
    assert status["embedder"] == "specter2"
