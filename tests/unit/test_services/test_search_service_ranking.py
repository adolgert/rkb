"""Tests for document ranking metrics (Phase 2)."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import ChunkResult, DocumentScore
from rkb.services.search_service import SearchService


class TestRankingMetrics:
    """Tests for rank_by_similarity and rank_by_relevance methods."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        with DocumentRegistry(db_path) as registry:
            yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.embed.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]])
        return embedder

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        return [
            # Document 1: 3 chunks with varying scores
            ChunkResult(
                chunk_id="chunk_1_1",
                content="content 1-1",
                similarity=0.9,
                distance=0.1,
                metadata={"doc_id": "doc_1", "page_numbers": [1]},
            ),
            ChunkResult(
                chunk_id="chunk_1_2",
                content="content 1-2",
                similarity=0.6,
                distance=0.4,
                metadata={"doc_id": "doc_1", "page_numbers": [2]},
            ),
            ChunkResult(
                chunk_id="chunk_1_3",
                content="content 1-3",
                similarity=0.3,
                distance=0.7,
                metadata={"doc_id": "doc_1", "page_numbers": [3]},
            ),
            # Document 2: 2 chunks, both high score
            ChunkResult(
                chunk_id="chunk_2_1",
                content="content 2-1",
                similarity=0.85,
                distance=0.15,
                metadata={"doc_id": "doc_2", "page_numbers": [1]},
            ),
            ChunkResult(
                chunk_id="chunk_2_2",
                content="content 2-2",
                similarity=0.8,
                distance=0.2,
                metadata={"doc_id": "doc_2", "page_numbers": [2]},
            ),
            # Document 3: 1 chunk, medium score
            ChunkResult(
                chunk_id="chunk_3_1",
                content="content 3-1",
                similarity=0.7,
                distance=0.3,
                metadata={"doc_id": "doc_3", "page_numbers": [1]},
            ),
        ]

    def test_rank_by_similarity_max_pooling(self, temp_db, mock_embedder, sample_chunks):
        """Test similarity ranking uses max pooling correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)
            ranked = service.rank_by_similarity(sample_chunks)

            # Should have 3 documents
            assert len(ranked) == 3

            # Check ranking order (by max score): doc_1 (0.9), doc_2 (0.85), doc_3 (0.7)
            assert ranked[0].doc_id == "doc_1"
            assert ranked[0].score == 0.9
            assert ranked[0].metric_name == "similarity"

            assert ranked[1].doc_id == "doc_2"
            assert ranked[1].score == 0.85

            assert ranked[2].doc_id == "doc_3"
            assert ranked[2].score == 0.7

            service.close()

    def test_rank_by_similarity_best_chunk_score_populated(
        self, temp_db, mock_embedder, sample_chunks
    ):
        """Test best_chunk_score field is populated correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)
            ranked = service.rank_by_similarity(sample_chunks)

            # Check best_chunk_score matches the score
            for doc_score in ranked:
                assert doc_score.best_chunk_score == doc_score.score

            service.close()

    def test_rank_by_relevance_hit_counting(self, temp_db, mock_embedder, sample_chunks):
        """Test relevance ranking uses hit counting correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)

            # Threshold 0.5: doc_1 has 2 hits, doc_2 has 2 hits, doc_3 has 1 hit
            ranked = service.rank_by_relevance(sample_chunks, min_threshold=0.5)

            assert len(ranked) == 3

            # doc_1 and doc_2 tie at 2 hits each, sorted by best_chunk_score (0.9 > 0.85)
            assert ranked[0].doc_id == "doc_1"
            assert ranked[0].score == 2.0  # 2 chunks above threshold
            assert ranked[0].metric_name == "relevance"

            assert ranked[1].doc_id == "doc_2"
            assert ranked[1].score == 2.0

            assert ranked[2].doc_id == "doc_3"
            assert ranked[2].score == 1.0

            service.close()

    def test_rank_by_relevance_matching_chunk_count(
        self, temp_db, mock_embedder, sample_chunks
    ):
        """Test matching_chunk_count field is populated correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)
            ranked = service.rank_by_relevance(sample_chunks, min_threshold=0.5)

            # Check matching_chunk_count equals the score (hit count)
            for doc_score in ranked:
                assert doc_score.matching_chunk_count == int(doc_score.score)

            service.close()

    def test_tie_breaking_similarity(self, temp_db, mock_embedder):
        """Test tie-breaking in similarity ranking (deterministic order by doc_id)."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            # Two documents with identical max scores
            chunks = [
                ChunkResult(
                    chunk_id="chunk_a",
                    content="content a",
                    similarity=0.8,
                    distance=0.2,
                    metadata={"doc_id": "doc_a"},
                ),
                ChunkResult(
                    chunk_id="chunk_b",
                    content="content b",
                    similarity=0.8,
                    distance=0.2,
                    metadata={"doc_id": "doc_b"},
                ),
            ]

            service = SearchService(registry=temp_db)
            ranked = service.rank_by_similarity(chunks)

            # Both should have same score
            assert ranked[0].score == 0.8
            assert ranked[1].score == 0.8

            # Order is determined by Python's stable sort (preserves original order)
            assert ranked[0].doc_id in ["doc_a", "doc_b"]
            assert ranked[1].doc_id in ["doc_a", "doc_b"]

            service.close()

    def test_single_chunk_documents(self, temp_db, mock_embedder):
        """Test ranking with single-chunk documents."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="content 1",
                    similarity=0.9,
                    distance=0.1,
                    metadata={"doc_id": "doc_1"},
                ),
                ChunkResult(
                    chunk_id="chunk_2",
                    content="content 2",
                    similarity=0.7,
                    distance=0.3,
                    metadata={"doc_id": "doc_2"},
                ),
            ]

            service = SearchService(registry=temp_db)

            # Test similarity ranking
            ranked_sim = service.rank_by_similarity(chunks)
            assert len(ranked_sim) == 2
            assert ranked_sim[0].score == 0.9
            assert ranked_sim[1].score == 0.7

            # Test relevance ranking
            ranked_rel = service.rank_by_relevance(chunks, min_threshold=0.5)
            assert len(ranked_rel) == 2
            assert ranked_rel[0].score == 1.0  # 1 chunk above threshold
            assert ranked_rel[1].score == 1.0

            service.close()

    def test_multi_chunk_documents(self, temp_db, mock_embedder, sample_chunks):
        """Test ranking with multi-chunk documents."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)

            # All sample chunks have multiple chunks per document
            ranked = service.rank_by_similarity(sample_chunks)

            # Verify chunk counts are tracked
            assert ranked[0].matching_chunk_count == 3  # doc_1 has 3 chunks
            assert ranked[1].matching_chunk_count == 2  # doc_2 has 2 chunks
            assert ranked[2].matching_chunk_count == 1  # doc_3 has 1 chunk

            service.close()

    def test_no_chunks_above_threshold(self, temp_db, mock_embedder):
        """Test edge case: no chunks above threshold."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="content 1",
                    similarity=0.1,
                    distance=9.0,
                    metadata={"doc_id": "doc_1"},
                ),
                ChunkResult(
                    chunk_id="chunk_2",
                    content="content 2",
                    similarity=0.05,
                    distance=19.0,
                    metadata={"doc_id": "doc_2"},
                ),
            ]

            service = SearchService(registry=temp_db)

            # High threshold - no chunks should match
            ranked = service.rank_by_relevance(chunks, min_threshold=0.5)

            # Should still return documents, but with 0 hits
            assert len(ranked) == 2
            assert ranked[0].score == 0.0
            assert ranked[1].score == 0.0

            service.close()

    def test_empty_chunks_list(self, temp_db, mock_embedder):
        """Test ranking with empty chunks list."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            service = SearchService(registry=temp_db)

            ranked_sim = service.rank_by_similarity([])
            assert len(ranked_sim) == 0

            ranked_rel = service.rank_by_relevance([], min_threshold=0.5)
            assert len(ranked_rel) == 0

            service.close()

    def test_chunks_without_doc_id(self, temp_db, mock_embedder):
        """Test ranking handles chunks without doc_id metadata."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="content 1",
                    similarity=0.9,
                    distance=0.1,
                    metadata={"doc_id": "doc_1"},
                ),
                ChunkResult(
                    chunk_id="chunk_2",
                    content="content 2",
                    similarity=0.8,
                    distance=0.2,
                    metadata={},  # No doc_id
                ),
            ]

            service = SearchService(registry=temp_db)

            # Should only rank chunks with doc_id
            ranked = service.rank_by_similarity(chunks)
            assert len(ranked) == 1
            assert ranked[0].doc_id == "doc_1"

            service.close()


class TestDisplayDataFetcher:
    """Tests for get_display_data method (Phase 2.5)."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        with DocumentRegistry(db_path) as registry:
            yield registry

        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        return Mock()

    def test_top_chunk_strategy_returns_best_chunk(self, temp_db, mock_embedder):
        """Test 'top_chunk' strategy returns best chunk."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="low score chunk",
                    similarity=0.5,
                    distance=1.0,
                    metadata={"doc_id": "doc_1", "page_numbers": [1]},
                ),
                ChunkResult(
                    chunk_id="chunk_2",
                    content="high score chunk",
                    similarity=0.9,
                    distance=0.1,
                    metadata={"doc_id": "doc_1", "page_numbers": [5]},
                ),
            ]

            doc_score = DocumentScore(
                doc_id="doc_1",
                score=0.9,
                metric_name="similarity",
            )

            service = SearchService(registry=temp_db)
            display_data = service.get_display_data(doc_score, chunks, strategy="top_chunk")

            # Should return the chunk with highest similarity
            assert display_data["chunk_text"] == "high score chunk"
            assert display_data["chunk_score"] == 0.9
            assert display_data["chunk_id"] == "chunk_2"
            assert display_data["page_numbers"] == [5]

            service.close()

    def test_display_data_includes_required_fields(self, temp_db, mock_embedder):
        """Test returned data includes: text, page, score."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="test content",
                    similarity=0.8,
                    distance=0.2,
                    metadata={"doc_id": "doc_1", "page_numbers": [3, 4]},
                ),
            ]

            doc_score = DocumentScore(doc_id="doc_1", score=0.8, metric_name="similarity")

            service = SearchService(registry=temp_db)
            display_data = service.get_display_data(doc_score, chunks)

            # Check all required fields are present
            assert "chunk_text" in display_data
            assert "chunk_score" in display_data
            assert "page_numbers" in display_data
            assert "chunk_id" in display_data

            assert display_data["chunk_text"] == "test content"
            assert display_data["chunk_score"] == 0.8
            assert display_data["page_numbers"] == [3, 4]

            service.close()

    def test_document_not_in_chunk_list(self, temp_db, mock_embedder):
        """Test with document not in chunk list (graceful handling)."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="content",
                    similarity=0.8,
                    distance=0.2,
                    metadata={"doc_id": "doc_other"},
                ),
            ]

            doc_score = DocumentScore(doc_id="doc_not_found", score=0.8, metric_name="similarity")

            service = SearchService(registry=temp_db)
            display_data = service.get_display_data(doc_score, chunks)

            # Should return error information
            assert display_data["chunk_text"] is None
            assert display_data["chunk_score"] is None
            assert display_data["page_numbers"] == []
            assert "error" in display_data

            service.close()

    def test_single_chunk_document(self, temp_db, mock_embedder):
        """Test with document with single chunk."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="only chunk",
                    similarity=0.7,
                    distance=0.3,
                    metadata={"doc_id": "doc_1", "page_numbers": [1]},
                ),
            ]

            doc_score = DocumentScore(doc_id="doc_1", score=0.7, metric_name="similarity")

            service = SearchService(registry=temp_db)
            display_data = service.get_display_data(doc_score, chunks)

            assert display_data["chunk_text"] == "only chunk"
            assert display_data["chunk_score"] == 0.7

            service.close()

    def test_multiple_chunks_returns_best(self, temp_db, mock_embedder):
        """Test with document with multiple chunks returns best."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder):
            chunks = [
                ChunkResult(
                    chunk_id="chunk_1",
                    content="chunk 1",
                    similarity=0.6,
                    distance=0.4,
                    metadata={"doc_id": "doc_1", "page_numbers": [1]},
                ),
                ChunkResult(
                    chunk_id="chunk_2",
                    content="chunk 2",
                    similarity=0.9,
                    distance=0.1,
                    metadata={"doc_id": "doc_1", "page_numbers": [2]},
                ),
                ChunkResult(
                    chunk_id="chunk_3",
                    content="chunk 3",
                    similarity=0.7,
                    distance=0.3,
                    metadata={"doc_id": "doc_1", "page_numbers": [3]},
                ),
            ]

            doc_score = DocumentScore(doc_id="doc_1", score=0.9, metric_name="similarity")

            service = SearchService(registry=temp_db)
            display_data = service.get_display_data(doc_score, chunks)

            # Should return chunk_2 (highest score)
            assert display_data["chunk_text"] == "chunk 2"
            assert display_data["chunk_score"] == 0.9
            assert display_data["chunk_id"] == "chunk_2"

            service.close()
