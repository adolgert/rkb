"""Tests for Chroma embedder."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.embedders.chroma_embedder import ChromaEmbedder


class TestChromaEmbedder:
    """Tests for ChromaEmbedder."""

    def test_embedder_initialization(self):
        """Test embedder initialization with default values."""
        embedder = ChromaEmbedder()

        assert embedder.collection_name == "academic_papers"
        assert embedder.db_path == Path("chroma_db")
        assert embedder.model_name == "all-MiniLM-L6-v2"

    def test_embedder_initialization_with_params(self):
        """Test embedder initialization with custom parameters."""
        embedder = ChromaEmbedder(
            collection_name="test_collection",
            db_path="/tmp/test_db",
            model_name="all-mpnet-base-v2",
        )

        assert embedder.collection_name == "test_collection"
        assert embedder.db_path == Path("/tmp/test_db")
        assert embedder.model_name == "all-mpnet-base-v2"

    def test_properties(self):
        """Test embedder properties."""
        embedder = ChromaEmbedder()

        assert embedder.name == "chroma"
        assert embedder.version == "1.0.0"

    def test_get_capabilities(self):
        """Test get_capabilities method."""
        embedder = ChromaEmbedder()
        capabilities = embedder.get_capabilities()

        assert capabilities["name"] == "chroma"
        assert capabilities["description"]
        assert "all-MiniLM-L6-v2" in capabilities["supported_models"]
        assert "persistent_storage" in capabilities["features"]
        assert "collection_name" in capabilities["configuration"]

    def test_embed_empty_texts(self):
        """Test embedding empty text list."""
        embedder = ChromaEmbedder()
        result = embedder.embed([])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert result.embedder_name == "chroma"

    def test_embed_import_error(self):
        """Test embedding when ChromaDB is not installed."""
        with patch("rkb.embedders.chroma_embedder.chromadb", side_effect=ImportError("No module")):
            embedder = ChromaEmbedder()
            result = embedder.embed(["test text"])

            assert result.embeddings == []
            assert result.chunk_count == 0
            assert "ChromaDB not installed" in result.error_message

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_embed_successful_new_collection(self, mock_chromadb):
        """Test successful embedding with new collection."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        # Simulate collection not existing, then created
        mock_client.get_collection.side_effect = ValueError("Collection not found")
        mock_client.create_collection.return_value = mock_collection

        # Mock the get method to return embeddings
        mock_collection.get.return_value = {
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = ChromaEmbedder(db_path=temp_dir)
            result = embedder.embed(["text1", "text2"])

            assert len(result.embeddings) == 2
            assert result.embeddings[0] == [0.1, 0.2, 0.3]
            assert result.chunk_count == 2
            assert result.embedder_name == "chroma"

            # Verify collection was created
            mock_client.create_collection.assert_called_once()

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_embed_successful_existing_collection(self, mock_chromadb):
        """Test successful embedding with existing collection."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        # Simulate collection exists
        mock_client.get_collection.return_value = mock_collection

        # Mock the get method to return embeddings
        mock_collection.get.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = ChromaEmbedder(db_path=temp_dir)
            result = embedder.embed(["text1"])

            assert len(result.embeddings) == 1
            assert result.embeddings[0] == [0.1, 0.2, 0.3]
            assert result.chunk_count == 1

            # Verify collection was not created (already existed)
            mock_client.create_collection.assert_not_called()

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_embed_chroma_error(self, mock_chromadb):
        """Test embedding with Chroma error."""
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_collection.side_effect = Exception("Chroma error")

        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = ChromaEmbedder(db_path=temp_dir)
            result = embedder.embed(["test text"])

            assert result.embeddings == []
            assert result.chunk_count == 0
            assert "Chroma error" in result.error_message

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_embed_single_successful(self, mock_chromadb):
        """Test successful single text embedding."""
        # Setup mocks
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_collection.return_value = mock_collection
        mock_collection.get.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = ChromaEmbedder(db_path=temp_dir)
            embedding = embedder.embed_single("test text")

            assert embedding == [0.1, 0.2, 0.3]

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_embed_single_error(self, mock_chromadb):
        """Test single text embedding with error."""
        mock_chromadb.PersistentClient.side_effect = Exception("Chroma error")

        embedder = ChromaEmbedder()
        with pytest.raises(RuntimeError, match="Chroma error"):
            embedder.embed_single("test text")

    @patch("rkb.embedders.chroma_embedder.chromadb")
    @patch("rkb.embedders.chroma_embedder.shutil")
    def test_test_connection_success(self, mock_shutil, mock_chromadb):
        """Test successful connection test."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.create_collection.return_value = mock_collection

        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = ChromaEmbedder(db_path=temp_dir)
            assert embedder.test_connection() is True

    def test_test_connection_import_error(self):
        """Test connection test with import error."""
        with patch("rkb.embedders.chroma_embedder.chromadb", side_effect=ImportError("No module")):
            embedder = ChromaEmbedder()
            assert embedder.test_connection() is False

    @patch("rkb.embedders.chroma_embedder.chromadb")
    def test_test_connection_chroma_error(self, mock_chromadb):
        """Test connection test with Chroma error."""
        mock_chromadb.PersistentClient.side_effect = Exception("Chroma error")

        embedder = ChromaEmbedder()
        assert embedder.test_connection() is False