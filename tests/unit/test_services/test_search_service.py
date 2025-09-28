"""Tests for search service functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import SearchResult, ChunkResult
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
            "documents": [["test document content", "another document"]],
            "metadatas": [[{"pdf_name": "test.pdf", "chunk_index": 0, "has_equations": True},
                          {"pdf_name": "test2.pdf", "chunk_index": 1, "has_equations": False}]],
            "distances": [[0.2, 0.3]],
            "ids": [["chunk_1", "chunk_2"]],
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

    def test_search_documents_success(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test successful document search."""
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

            # Mock Chroma client
            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            result = service.search_documents("test query", n_results=2)

            assert isinstance(result, SearchResult)
            assert result.query == "test query"
            assert result.total_results == 2
            assert len(result.chunk_results) == 2
            assert result.error_message is None

            # Check chunk results
            chunk1 = result.chunk_results[0]
            assert chunk1.content == "test document content"
            assert chunk1.similarity == 0.8  # 1 - 0.2
            assert chunk1.metadata["pdf_name"] == "test.pdf"

    def test_search_documents_with_filters(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test document search with filters."""
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            result = service.search_documents(
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
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

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
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            service = SearchService(registry=temp_db)
            result = service.search_by_document("test query", "doc123")

            # Verify document filter was applied
            mock_chroma_collection.query.assert_called_once()
            call_args = mock_chroma_collection.query.call_args
            where_filter = call_args.kwargs["where"]
            assert where_filter["doc_id"] == {"$in": ["doc123"]}

    def test_get_similar_chunks(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test finding similar chunks."""
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

            mock_client.return_value.get_collection.return_value = mock_chroma_collection

            # Mock get method for reference chunk
            mock_chroma_collection.get.return_value = {
                "documents": ["reference chunk content"],
                "metadatas": [{"doc_id": "ref_doc", "pdf_name": "ref.pdf"}],
            }

            service = SearchService(registry=temp_db)
            result = service.get_similar_chunks("ref_chunk_id", n_results=3)

            # Verify reference chunk was retrieved
            mock_chroma_collection.get.assert_called_once_with(ids=["ref_chunk_id"])

            # Verify similarity search was performed
            assert mock_chroma_collection.query.called
            call_args = mock_chroma_collection.query.call_args
            assert call_args.kwargs["query_texts"] == ["reference chunk content"]

    def test_get_database_stats(self, temp_db, mock_chroma_collection, mock_embedder):
        """Test getting database statistics."""
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

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
        with patch('rkb.services.search_service.get_embedder', return_value=mock_embedder), \
             patch('rkb.services.search_service.chromadb.PersistentClient') as mock_client:

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