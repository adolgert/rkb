"""Tests for Chroma embedder."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from rkb.embedders.chroma_embedder import ChromaEmbedder


class TestChromaEmbedder:
    """Tests for ChromaEmbedder."""

    def test_embedder_initialization(self):
        """Test embedder initialization with default values."""
        embedder = ChromaEmbedder()

        assert embedder.collection_name == "documents"
        assert embedder.db_path == Path("rkb_chroma_db")
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
        # Remove chromadb from sys.modules if it exists
        chromadb_module = sys.modules.pop("chromadb", None)

        try:
            with patch.dict(sys.modules, {"chromadb": None}):
                embedder = ChromaEmbedder()
                result = embedder.embed(["test text"])

                assert result.embeddings == []
                assert result.chunk_count == 0
                assert "ChromaDB not installed" in result.error_message
        finally:
            # Restore chromadb module if it existed
            if chromadb_module is not None:
                sys.modules["chromadb"] = chromadb_module

    def test_embed_successful_new_collection(self):
        """Test successful embedding with new collection."""
        # Setup mocks
        mock_chromadb = MagicMock()
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_chromadb.errors.NotFoundError = Exception  # Mock the exception type

        # Simulate collection not existing, then created
        error_msg = "Collection not found"
        mock_client.get_collection.side_effect = mock_chromadb.errors.NotFoundError(error_msg)
        mock_client.create_collection.return_value = mock_collection

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(sys.modules, {"chromadb": mock_chromadb}):
                embedder = ChromaEmbedder(db_path=temp_dir)
                result = embedder.embed(["text1", "text2"])

                assert result.embeddings == []  # ChromaDB stores embeddings internally
                assert result.chunk_count == 2
                assert result.embedder_name == "chroma"
                assert result.error_message is None

                # Verify collection was created
                mock_client.create_collection.assert_called_once()

    def test_embed_successful_existing_collection(self):
        """Test successful embedding with existing collection."""
        # Setup mocks
        mock_chromadb = MagicMock()
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_chromadb.errors.NotFoundError = Exception

        # Simulate collection exists
        mock_client.get_collection.return_value = mock_collection

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(sys.modules, {"chromadb": mock_chromadb}):
                embedder = ChromaEmbedder(db_path=temp_dir)
                result = embedder.embed(["text1"])

                assert result.embeddings == []  # ChromaDB stores embeddings internally
                assert result.chunk_count == 1
                assert result.embedder_name == "chroma"
                assert result.error_message is None

                # Verify collection was not created (already existed)
                mock_client.create_collection.assert_not_called()


