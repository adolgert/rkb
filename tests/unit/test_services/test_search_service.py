"""Tests for search service functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import ChunkResult, SearchResult
from rkb.services.search_service import SearchService


class TestSearchService:
    """Tests for SearchService."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def mock_chroma_collection(self):
        """Create mock Chroma collection."""
        collection = Mock()
        collection.count.return_value = 100
        collection.query.return_value = {
            "documents": [[
                "test document content",
                "another document",
                "far document",
                "very far document",
            ]],
            "metadatas": [[{"pdf_name": "test.pdf", "chunk_index": 0, "has_equations": True},
                          {"pdf_name": "test2.pdf", "chunk_index": 1, "has_equations": False},
                          {"pdf_name": "test3.pdf", "chunk_index": 2, "has_equations": True},
                          {"pdf_name": "test4.pdf", "chunk_index": 3, "has_equations": False}]],
            "distances": [[0.2, 0.3, 1.5, 2.0]],  # Include distances > 1.0 to test the fix
            "ids": [["chunk_1", "chunk_2", "chunk_3", "chunk_4"]],
        }
        return collection

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.embed.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]])
        return embedder

    def test_initialization(self, temp_db):
        """Test SearchService initialization."""
        service = SearchService(
            db_path="test_db",
            collection_name="test_collection",
            embedder_name="chroma",
            registry=temp_db,
        )

        assert service.db_path == Path("test_db")
        assert service.collection_name == "test_collection"
        assert service.embedder_name == "chroma"
        assert service.registry == temp_db

    def test_similarity_conversion(self):
        """Test distance to similarity conversion using inverse distance formula."""
        # Test cases for the similarity calculation: similarity = 1 / (1 + distance)
        test_cases = [
            (0.0, 1.0),      # Perfect match: distance 0 → similarity 1.0
            (0.2, 0.833),    # Good match: distance 0.2 → similarity ~0.833
            (1.0, 0.5),      # Medium match: distance 1.0 → similarity 0.5
            (1.066, 0.484),  # Real data case: distance 1.066 → similarity ~0.484
            (2.0, 0.333),    # Poor match: distance 2.0 → similarity ~0.333
            (5.0, 0.167),    # Very poor match: distance 5.0 → similarity ~0.167
        ]

        for distance, expected_similarity in test_cases:
            # Test the actual formula used in search_service.py
            similarity = 1 / (1 + distance)
            assert abs(similarity - expected_similarity) < 0.001, (
                f"Distance {distance} should give similarity ~{expected_similarity}, "
                f"got {similarity}"
            )

            # Verify similarity is always in [0, 1] range
            assert 0 <= similarity <= 1, f"Similarity {similarity} not in [0,1] range"

        # Test None distance case
        distance = None
        similarity = 1 / (1 + distance) if distance is not None else 0.0
        assert similarity == 0.0, "None distance should give similarity 0.0"

    def test_search_documents_success(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test successful document search."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Mock Chroma client
            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            result = service.search_documents("test query", n_results=4)

            assert isinstance(result, SearchResult)
            assert result.query == "test query"
            assert result.total_results == 4
            assert len(result.chunk_results) == 4
            assert result.error_message is None

            # Check chunk results with different distances
            chunk1 = result.chunk_results[0]
            assert chunk1.content == "test document content"
            assert abs(chunk1.similarity - 0.833) < 0.001  # 1 / (1 + 0.2) ≈ 0.833
            assert chunk1.metadata["pdf_name"] == "test.pdf"

            # Check that distances > 1.0 produce reasonable similarity scores
            chunk3 = result.chunk_results[2]  # distance 1.5
            expected_similarity_3 = 1 / (1 + 1.5)  # = 0.4
            assert abs(chunk3.similarity - expected_similarity_3) < 0.001
            assert chunk3.content == "far document"

            chunk4 = result.chunk_results[3]  # distance 2.0
            expected_similarity_4 = 1 / (1 + 2.0)  # ≈ 0.333
            assert abs(chunk4.similarity - expected_similarity_4) < 0.001
            assert chunk4.content == "very far document"

            # Verify all similarities are in [0, 1] range
            for chunk in result.chunk_results:
                assert (
                    0 <= chunk.similarity <= 1
                ), f"Similarity {chunk.similarity} not in [0,1] range"

    def test_search_documents_with_filters(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test document search with filters."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            service.search_documents(
                "test query",
                filter_equations=True,
                project_id="test_project",
                document_ids=["doc1", "doc2"],
            )

            # Verify filters were applied
            mock_chroma_collection.query.assert_called_once()
            call_args = mock_chroma_collection.query.call_args
            assert "where" in call_args.kwargs
            where_filter = call_args.kwargs["where"]
            assert where_filter["has_equations"] is True
            assert where_filter["project_id"] == "test_project"
            assert where_filter["doc_id"] == {"$in": ["doc1", "doc2"]}

    def test_search_documents_error(self, temp_db, mock_embedder):
        """Test search error handling."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            # Mock Chroma to raise exception for both get and create
            mock_client.return_value.get_collection.side_effect = Exception("Connection failed")
            mock_client.return_value.create_collection.side_effect = Exception("Connection failed")

            service = SearchService(registry=temp_db)
            result = service.search_documents("test query")

            assert isinstance(result, SearchResult)
            assert result.total_results == 0
            assert result.error_message == "Connection failed"

    def test_search_by_document(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test searching within a specific document."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            service.search_by_document("test query", "doc123")

            # Verify document filter was applied
            mock_chroma_collection.query.assert_called_once()
            call_args = mock_chroma_collection.query.call_args
            where_filter = call_args.kwargs["where"]
            assert where_filter["doc_id"] == {"$in": ["doc123"]}

    def test_get_similar_chunks(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test finding similar chunks."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            # Mock get method for reference chunk
            mock_chroma_collection.get.return_value = {
                "documents": ["reference chunk content"],
                "metadatas": [{"doc_id": "ref_doc", "pdf_name": "ref.pdf"}],
            }

            service = SearchService(registry=temp_db)
            service.get_similar_chunks("ref_chunk_id", n_results=3)

            # Verify reference chunk was retrieved
            mock_chroma_collection.get.assert_called_once_with(ids=["ref_chunk_id"])

            # Verify similarity search was performed
            assert mock_chroma_collection.query.called
            call_args = mock_chroma_collection.query.call_args
            assert call_args.kwargs["query_texts"] == ["reference chunk content"]

    def test_get_database_stats(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test getting database statistics."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            # Mock sample data for equation statistics
            mock_chroma_collection.get.return_value = {
                "metadatas": [
                    {"has_equations": True},
                    {"has_equations": False},
                    {"has_equations": True},
                    {"has_equations": False},
                ],
            }

            service = SearchService(registry=temp_db)
            stats = service.get_database_stats()

            assert stats["total_chunks"] == 100
            assert stats["equation_percentage"] == 50.0  # 2 out of 4 samples
            assert stats["collection_name"] == "documents"
            assert "registry_stats" in stats

    def test_test_search(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test the test search functionality."""
        with patch("rkb.services.search_service.get_embedder", return_value=mock_embedder), \
             patch("rkb.services.search_service.chromadb.PersistentClient") as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            result = service.test_search("machine learning")

            assert isinstance(result, SearchResult)
            assert result.query == "machine learning"
            assert result.total_results > 0

    def test_display_results(self, temp_db, capsys):
        """Test displaying search results."""
        service = SearchService(registry=temp_db)

        # Create test search result
        chunk_results = [
            ChunkResult(
                chunk_id="chunk1",
                content="This is test content about machine learning algorithms.",
                similarity=0.85,
                distance=0.15,
                metadata={"pdf_name": "test.pdf", "chunk_index": 0, "has_equations": True},
            ),
        ]

        search_result = SearchResult(
            query="machine learning",
            chunk_results=chunk_results,
            total_results=1,
        )

        service.display_results(search_result)

        captured = capsys.readouterr()
        assert "Found 1 results for: 'machine learning'" in captured.out
        assert "Source: test.pdf (chunk 0)" in captured.out
        assert "This is test content" in captured.out

    def test_display_results_no_results(self, temp_db, capsys):
        """Test displaying empty search results."""
        service = SearchService(registry=temp_db)

        search_result = SearchResult(
            query="nonexistent",
            chunk_results=[],
            total_results=0,
        )

        service.display_results(search_result)

        captured = capsys.readouterr()
        assert "No results found." in captured.out

    def test_display_results_with_error(self, temp_db, capsys):
        """Test displaying search results with error."""
        service = SearchService(registry=temp_db)

        search_result = SearchResult(
            query="test",
            chunk_results=[],
            total_results=0,
            error_message="Database connection failed",
        )

        service.display_results(search_result)

        captured = capsys.readouterr()
        assert "Search error: Database connection failed" in captured.out

