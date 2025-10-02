"""Tests for document-level search (iterative chunk fetching)."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.services.search_service import SearchService


class TestFetchChunksIteratively:
    """Tests for fetch_chunks_iteratively method (Phase 1: Core Loop)."""

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

    def test_finds_n_documents_in_first_fetch(self, temp_db, mock_embedder):
        """Test: Finds N documents in first fetch."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create mock collection with 10 documents (2 chunks each = 20 chunks)
            # All chunks above threshold 0.1
            mock_collection = Mock()
            documents = []
            metadatas = []
            distances = []
            ids = []

            for doc_idx in range(10):
                for chunk_idx in range(2):
                    documents.append(f"content from doc {doc_idx} chunk {chunk_idx}")
                    metadatas.append({
                        "doc_id": f"doc_{doc_idx}",
                        "chunk_index": chunk_idx,
                    })
                    # Good similarity: distance 0.1 = similarity ~0.91
                    distances.append(0.1)
                    ids.append(f"chunk_{doc_idx}_{chunk_idx}")

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
            )

            # Should find 10 documents in first fetch
            assert stats["documents_found"] == 10
            assert stats["iterations"] == 1
            assert len(chunks) == 20  # 10 docs x 2 chunks
            assert stats["chunks_above_threshold"] == 20

            service.close()

    def test_requires_multiple_fetches_to_find_n_documents(self, temp_db, mock_embedder):
        """Test: Requires multiple fetches to find N documents.

        Note: Since ChromaDB doesn't support offset-based pagination, this test
        verifies the implementation detail that we fetch everything in one go.
        In a real scenario with true pagination, we'd need multiple fetches.
        """
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create mock with 5 documents (need 10, but only 5 available)
            mock_collection = Mock()
            documents = []
            metadatas = []
            distances = []
            ids = []

            for doc_idx in range(5):
                for chunk_idx in range(2):
                    documents.append(f"content from doc {doc_idx} chunk {chunk_idx}")
                    metadatas.append({
                        "doc_id": f"doc_{doc_idx}",
                        "chunk_index": chunk_idx,
                    })
                    distances.append(0.1)
                    ids.append(f"chunk_{doc_idx}_{chunk_idx}")

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
            )

            # Should find only 5 documents (less than requested 10)
            assert stats["documents_found"] == 5
            assert stats["iterations"] == 1
            assert len(chunks) == 10  # 5 docs x 2 chunks

            service.close()

    def test_stops_when_exhausting_database(self, temp_db, mock_embedder):
        """Test: Stops when exhausting database (< N documents available)."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create mock with only 3 documents above threshold
            mock_collection = Mock()
            documents = []
            metadatas = []
            distances = []
            ids = []

            for doc_idx in range(3):
                documents.append(f"content from doc {doc_idx}")
                metadatas.append({
                    "doc_id": f"doc_{doc_idx}",
                    "chunk_index": 0,
                })
                distances.append(0.1)  # Above threshold
                ids.append(f"chunk_{doc_idx}_0")

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
            )

            # Should stop with only 3 documents (database exhausted)
            assert stats["documents_found"] == 3
            assert stats["iterations"] == 1
            assert len(chunks) == 3

            service.close()

    def test_respects_maximum_chunk_limit(self, temp_db, mock_embedder):
        """Test: Respects maximum chunk limit."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create mock that would return more than MAX_TOTAL_CHUNKS (10000)
            # But ChromaDB will limit to 10000
            mock_collection = Mock()

            # Create exactly 10000 chunks (limit)
            documents = [f"doc {i}" for i in range(10000)]
            metadatas = [{"doc_id": f"doc_{i}", "chunk_index": 0} for i in range(10000)]
            distances = [0.1] * 10000
            ids = [f"chunk_{i}" for i in range(10000)]

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=1000,  # Request many documents
                min_threshold=0.1,
            )

            # Should stop at MAX_TOTAL_CHUNKS (10000)
            assert len(chunks) <= 10000
            assert stats["chunks_fetched"] == 10000

            service.close()

    def test_handles_empty_database_gracefully(self, temp_db, mock_embedder):
        """Test: Handles empty database gracefully."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Mock empty collection
            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
            )

            # Should handle empty database gracefully
            assert len(chunks) == 0
            assert stats["documents_found"] == 0
            assert stats["iterations"] == 1
            assert stats["chunks_fetched"] == 0

            service.close()

    def test_handles_query_with_no_results_above_threshold(self, temp_db, mock_embedder):
        """Test: Handles query with no results above threshold."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create mock with chunks all below threshold
            mock_collection = Mock()
            documents = []
            metadatas = []
            distances = []
            ids = []

            for doc_idx in range(5):
                documents.append(f"content from doc {doc_idx}")
                metadatas.append({
                    "doc_id": f"doc_{doc_idx}",
                    "chunk_index": 0,
                })
                # High distance = low similarity (below threshold 0.5)
                # distance 5.0 = similarity 1/(1+5) = 0.167
                distances.append(5.0)
                ids.append(f"chunk_{doc_idx}_0")

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.5,  # High threshold
            )

            # Should find 0 documents above threshold
            assert stats["documents_found"] == 0
            assert stats["chunks_above_threshold"] == 0
            assert len(chunks) == 5  # But we still fetched 5 chunks
            assert stats["chunks_fetched"] == 5

            service.close()

    def test_threshold_filtering(self, temp_db, mock_embedder):
        """Test: Chunks are correctly filtered by threshold."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create chunks with varying similarity
            mock_collection = Mock()
            documents = ["high", "medium", "low", "very low"]
            metadatas = [
                {"doc_id": "doc_1", "chunk_index": 0},
                {"doc_id": "doc_2", "chunk_index": 0},
                {"doc_id": "doc_3", "chunk_index": 0},
                {"doc_id": "doc_4", "chunk_index": 0},
            ]
            # distances: 0.1 (sim ~0.91), 1.0 (sim 0.5), 3.0 (sim 0.25), 9.0 (sim 0.1)
            distances = [0.1, 1.0, 3.0, 9.0]
            ids = ["chunk_1", "chunk_2", "chunk_3", "chunk_4"]

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.3,  # Should filter out last 2 chunks
            )

            # Should have 2 chunks above threshold (0.91, 0.5)
            assert stats["chunks_above_threshold"] == 2
            assert stats["documents_found"] == 2
            assert len(chunks) == 4  # All chunks fetched

            service.close()

    def test_filters_applied_correctly(self, temp_db, mock_embedder):
        """Test: Filters (equations, project_id) are applied correctly."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_collection = Mock()
            mock_collection.query.return_value = {
                "documents": [["test"]],
                "metadatas": [[{"doc_id": "doc_1"}]],
                "distances": [[0.1]],
                "ids": [["chunk_1"]],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
                filter_equations=True,
                project_id="test_project",
            )

            # Verify filters were passed to ChromaDB
            mock_collection.query.assert_called_once()
            call_args = mock_collection.query.call_args
            assert "where" in call_args.kwargs
            where_filter = call_args.kwargs["where"]
            assert where_filter["has_equations"] is True
            assert where_filter["project_id"] == "test_project"

            service.close()

    def test_error_handling(self, temp_db, mock_embedder):
        """Test: Errors are handled gracefully."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Mock collection to raise exception
            mock_collection = Mock()
            mock_collection.query.side_effect = Exception("Database connection failed")

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.1,
            )

            # Should return empty results with error
            assert len(chunks) == 0
            assert stats["documents_found"] == 0
            assert "error" in stats
            assert stats["error"] == "Database connection failed"

            service.close()

    def test_statistics_accuracy(self, temp_db, mock_embedder):
        """Test: Statistics returned are accurate."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Create 3 documents with varying chunks
            mock_collection = Mock()
            documents = [
                "doc1_chunk1", "doc1_chunk2",  # doc_1: 2 chunks
                "doc2_chunk1",  # doc_2: 1 chunk
                "doc3_chunk1", "doc3_chunk2", "doc3_chunk3",  # doc_3: 3 chunks
            ]
            metadatas = [
                {"doc_id": "doc_1", "chunk_index": 0},
                {"doc_id": "doc_1", "chunk_index": 1},
                {"doc_id": "doc_2", "chunk_index": 0},
                {"doc_id": "doc_3", "chunk_index": 0},
                {"doc_id": "doc_3", "chunk_index": 1},
                {"doc_id": "doc_3", "chunk_index": 2},
            ]
            # Mix of above/below threshold (threshold 0.3)
            # distances: 0.1 (0.91), 2.0 (0.33), 3.0 (0.25), 0.2 (0.83), 4.0 (0.2), 0.15 (0.87)
            distances = [0.1, 2.0, 3.0, 0.2, 4.0, 0.15]
            ids = [f"chunk_{i}" for i in range(6)]

            mock_collection.query.return_value = {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
                "ids": [ids],
            }

            mock_client.return_value.get_collection.return_value = mock_collection

            service = SearchService(registry=temp_db)
            _chunks, stats = service.fetch_chunks_iteratively(
                query="test query",
                n_docs=10,
                min_threshold=0.3,
            )

            # Verify statistics
            assert stats["chunks_fetched"] == 6
            # Above threshold: chunk 0 (0.91), chunk 1 (0.33), chunk 3 (0.83), chunk 5 (0.87)
            assert stats["chunks_above_threshold"] == 4
            # Documents with chunks above threshold: doc_1, doc_3
            assert stats["documents_found"] == 2
            assert stats["iterations"] == 1

            service.close()
