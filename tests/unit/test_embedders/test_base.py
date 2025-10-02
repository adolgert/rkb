"""Tests for embedder base functionality."""


import pytest

from rkb.core.interfaces import EmbedderInterface
from rkb.core.models import EmbeddingResult
from rkb.embedders.base import get_embedder, list_embedders, register_embedder


class MockEmbedder(EmbedderInterface):
    """Mock embedder for testing."""

    @property
    def name(self) -> str:
        """Return the embedder name."""
        return "mock"

    @property
    def version(self) -> str:
        """Return the embedder version."""
        return "1.0.0"

    @property
    def minimum_threshold(self) -> float:
        """Return the minimum similarity threshold for mock embedder."""
        return 0.1

    def embed(self, text_chunks: list[str]) -> EmbeddingResult:
        """Mock embed method."""
        mock_embeddings = [[0.1, 0.2, 0.3] for _ in text_chunks]
        return EmbeddingResult(
            embedder_name=self.name,
            embedder_version=self.version,
            embeddings=mock_embeddings,
            chunk_count=len(mock_embeddings),
        )

    def get_embedding_dimension(self) -> int:
        """Mock embedding dimension."""
        return 3

    def get_configuration(self) -> dict:
        """Mock configuration."""
        return {
            "model_name": "mock",
            "dimension": 3,
            "max_tokens": 100,
            "batch_size": 10,
            "requires_gpu": False,
        }

    def get_capabilities(self) -> dict:
        """Mock capabilities."""
        return {"name": "mock", "features": ["test"]}


class TestEmbedderBase:
    """Tests for embedder base functionality."""

    def test_register_and_get_embedder(self):
        """Test registering and retrieving an embedder."""
        # Register mock embedder
        register_embedder("mock", MockEmbedder)

        # Check it's listed
        embedders = list_embedders()
        assert "mock" in embedders

        # Get the embedder
        embedder = get_embedder("mock")
        assert isinstance(embedder, MockEmbedder)

    def test_get_unknown_embedder_raises_error(self):
        """Test that getting unknown embedder raises ValueError."""
        with pytest.raises(ValueError, match="Unknown embedder 'nonexistent'"):
            get_embedder("nonexistent")

    def test_ollama_embedder_is_registered(self):
        """Test that OllamaEmbedder is automatically registered."""
        embedders = list_embedders()
        assert "ollama" in embedders

        # Get the ollama embedder
        embedder = get_embedder("ollama")
        assert embedder is not None

        # Check capabilities
        capabilities = embedder.get_capabilities()
        assert capabilities["name"] == "ollama"
        assert "mxbai-embed-large" in capabilities["supported_models"]

    def test_chroma_embedder_is_registered(self):
        """Test that ChromaEmbedder is automatically registered."""
        embedders = list_embedders()
        assert "chroma" in embedders

        # Get the chroma embedder
        embedder = get_embedder("chroma")
        assert embedder is not None

        # Check capabilities
        capabilities = embedder.get_capabilities()
        assert capabilities["name"] == "chroma"
        assert "all-MiniLM-L6-v2" in capabilities["supported_models"]
