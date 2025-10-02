"""Integration tests for complete document search workflow (Phase 3)."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentScore
from rkb.services.search_service import SearchService


class TestDocumentSearchIntegration:
    """Integration tests for search_documents_ranked method."""

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
        """Create mock embedder with minimum_threshold."""
        embedder = Mock()
        embedder.minimum_threshold = 0.3
        return embedder

    @pytest.fixture
    def sample_chunks_multi_doc(self):
        """Create sample chunks from multiple documents for realistic testing."""
        from rkb.core.models import ChunkResult

        # Document 1: High relevance (3 chunks, all above threshold)
        doc1_chunks = [
            ChunkResult(
                chunk_id="doc1_chunk1",
                content="Machine learning algorithms for classification",
                similarity=0.9,
                distance=0.1,
                metadata={"doc_id": "doc_1", "page_numbers": [1, 2]},
            ),
            ChunkResult(
                chunk_id="doc1_chunk2",
                content="Neural networks and deep learning",
                similarity=0.85,
                distance=0.15,
                metadata={"doc_id": "doc_1", "page_numbers": [3]},
            ),
            ChunkResult(
                chunk_id="doc1_chunk3",
                content="Training machine learning models",
                similarity=0.8,
                distance=0.2,
                metadata={"doc_id": "doc_1", "page_numbers": [4, 5]},
            ),
        ]

        # Document 2: Medium relevance (2 chunks above threshold, 1 below)
        doc2_chunks = [
            ChunkResult(
                chunk_id="doc2_chunk1",
                content="Statistical methods in data science",
                similarity=0.7,
                distance=0.3,
                metadata={"doc_id": "doc_2", "page_numbers": [1]},
            ),
            ChunkResult(
                chunk_id="doc2_chunk2",
                content="Bayesian inference techniques",
                similarity=0.6,
                distance=0.4,
                metadata={"doc_id": "doc_2", "page_numbers": [2]},
            ),
            ChunkResult(
                chunk_id="doc2_chunk3",
                content="Some unrelated content",
                similarity=0.2,
                distance=4.0,
                metadata={"doc_id": "doc_2", "page_numbers": [10]},
            ),
        ]

        # Document 3: Low relevance (1 chunk barely above threshold)
        doc3_chunks = [
            ChunkResult(
                chunk_id="doc3_chunk1",
                content="Introduction to statistics",
                similarity=0.35,
                distance=1.857,
                metadata={"doc_id": "doc_3", "page_numbers": [1]},
            ),
        ]

        return doc1_chunks + doc2_chunks + doc3_chunks

    def test_end_to_end_similarity_search(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test end-to-end: query → chunks → ranking → display data."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Mock collection
            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Execute complete workflow
            ranked_docs, all_chunks, stats = service.search_documents_ranked(
                query="machine learning",
                n_docs=3,
                metric="similarity",
            )

            # Verify we got 3 documents
            assert len(ranked_docs) == 3
            assert all(isinstance(doc, DocumentScore) for doc in ranked_docs)

            # Verify ranking order (by max similarity)
            assert ranked_docs[0].doc_id == "doc_1"  # max 0.9
            assert ranked_docs[1].doc_id == "doc_2"  # max 0.7
            assert ranked_docs[2].doc_id == "doc_3"  # max 0.35

            # Verify scores (approximately, due to distance->similarity conversion)
            assert abs(ranked_docs[0].score - 0.909) < 0.01  # 1/(1+0.1) ≈ 0.909
            assert abs(ranked_docs[1].score - 0.769) < 0.01  # 1/(1+0.3) ≈ 0.769
            assert abs(ranked_docs[2].score - 0.35) < 0.01  # 1/(1+1.857) ≈ 0.35

            # Verify we got all chunks back
            assert len(all_chunks) == 7

            # Verify stats
            assert stats["chunks_fetched"] == 7
            assert stats["documents_found"] == 3
            assert stats["iterations"] == 1

            service.close()

    def test_end_to_end_relevance_search(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test end-to-end with relevance metric."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Execute with relevance metric (threshold 0.3 from embedder)
            ranked_docs, _all_chunks, _stats = service.search_documents_ranked(
                query="machine learning",
                n_docs=3,
                metric="relevance",
            )

            # With threshold 0.3:
            # - doc_1: 3 hits (0.9, 0.85, 0.8)
            # - doc_2: 2 hits (0.7, 0.6)
            # - doc_3: 1 hit (0.35)
            assert len(ranked_docs) == 3
            assert ranked_docs[0].doc_id == "doc_1"
            assert ranked_docs[0].score == 3.0  # 3 chunks above threshold
            assert ranked_docs[1].doc_id == "doc_2"
            assert ranked_docs[1].score == 2.0
            assert ranked_docs[2].doc_id == "doc_3"
            assert ranked_docs[2].score == 1.0

            service.close()

    def test_display_data_integration(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test display data fetcher with search results."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Get search results
            ranked_docs, all_chunks, _stats = service.search_documents_ranked(
                query="machine learning",
                n_docs=3,
                metric="similarity",
            )

            # Get display data for top document
            top_doc = ranked_docs[0]
            display_data = service.get_display_data(top_doc, all_chunks)

            # Should return best chunk from doc_1
            assert display_data["chunk_text"] == "Machine learning algorithms for classification"
            assert abs(display_data["chunk_score"] - 0.909) < 0.01  # 1/(1+0.1)
            assert display_data["page_numbers"] == [1, 2]
            assert display_data["chunk_id"] == "doc1_chunk1"

            service.close()

    def test_custom_threshold_override(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test custom threshold overrides embedder default."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Use high threshold (0.7) - should filter out more chunks
            ranked_docs, _all_chunks, stats = service.search_documents_ranked(
                query="machine learning",
                n_docs=3,
                metric="relevance",
                min_threshold=0.7,
            )

            # With threshold 0.7:
            # Distance->similarity: 0.1->0.909, 0.15->0.870, 0.2->0.833, 0.3->0.769, 0.4->0.714
            # - doc_1: 3 hits (0.909, 0.870, 0.833)
            # - doc_2: 2 hits (0.769, 0.714) - both >= 0.7
            # - doc_3: 0 hits (0.35 < 0.7)
            assert ranked_docs[0].score == 3.0
            assert ranked_docs[1].score == 2.0  # doc_2 has 2 chunks >= 0.7
            assert ranked_docs[2].score == 0.0

            # Verify fewer chunks above threshold
            assert stats["chunks_above_threshold"] == 5  # 5 chunks >= 0.7

            service.close()

    def test_filters_applied_in_integration(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test filters (equations, project_id) work end-to-end."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Search with filters
            service.search_documents_ranked(
                query="machine learning",
                n_docs=3,
                metric="similarity",
                filter_equations=True,
                project_id="test_project",
            )

            # Verify filters were passed through to ChromaDB
            mock_collection.query.assert_called_once()
            call_kwargs = mock_collection.query.call_args.kwargs
            assert "where" in call_kwargs
            assert call_kwargs["where"]["has_equations"] is True
            assert call_kwargs["where"]["project_id"] == "test_project"

            service.close()

    def test_invalid_metric_raises_error(self, temp_db, mock_embedder):
        """Test invalid metric raises ValueError."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            with pytest.raises(ValueError, match="Unknown metric 'invalid'"):
                service.search_documents_ranked(
                    query="test",
                    metric="invalid",
                )

            service.close()

    def test_n_docs_parameter_limits_results(
        self, temp_db, mock_embedder, sample_chunks_multi_doc
    ):
        """Test n_docs parameter correctly limits returned documents."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[chunk.content for chunk in sample_chunks_multi_doc]],
                "metadatas": [[chunk.metadata for chunk in sample_chunks_multi_doc]],
                "distances": [[chunk.distance for chunk in sample_chunks_multi_doc]],
                "ids": [[chunk.chunk_id for chunk in sample_chunks_multi_doc]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            # Request only top 2 documents
            ranked_docs, _all_chunks, _stats = service.search_documents_ranked(
                query="machine learning",
                n_docs=2,
                metric="similarity",
            )

            # Should return exactly 2 documents (top ranked)
            assert len(ranked_docs) == 2
            assert ranked_docs[0].doc_id == "doc_1"
            assert ranked_docs[1].doc_id == "doc_2"

            service.close()

    def test_empty_results_handled_gracefully(self, temp_db, mock_embedder):
        """Test empty search results are handled correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]],
            }
            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)

            ranked_docs, all_chunks, stats = service.search_documents_ranked(
                query="nonexistent query",
                n_docs=10,
                metric="similarity",
            )

            # Should handle empty results gracefully
            assert len(ranked_docs) == 0
            assert len(all_chunks) == 0
            assert stats["documents_found"] == 0
            assert stats["chunks_fetched"] == 0

            service.close()
