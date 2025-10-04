"""Ollama-based embedder for generating text embeddings."""

from datetime import datetime
from typing import Any

import requests

from rkb.core.interfaces import EmbedderInterface
from rkb.core.models import EmbeddingResult
from rkb.embedders.base import register_embedder


class OllamaEmbedder(EmbedderInterface):
    """Ollama-based embedder for generating text embeddings."""

    def __init__(
        self,
        model: str = "mxbai-embed-large",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
        batch_size: int = 100,
    ):
        """Initialize Ollama embedder.

        Args:
            model: Ollama model name for embeddings
            base_url: Base URL for Ollama service
            timeout: Request timeout in seconds
            batch_size: Maximum number of texts to embed in one batch
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size
        self._embeddings_url = f"{self.base_url}/api/embeddings"

    @property
    def name(self) -> str:
        """Return the embedder name."""
        return "ollama"

    @property
    def version(self) -> str:
        """Return the embedder version."""
        return "1.0.0"

    @property
    def minimum_threshold(self) -> float:
        """Return the minimum similarity threshold for Ollama embeddings.

        For Ollama embedding models, a similarity of 0.1 is a reasonable
        threshold for filtering out irrelevant chunks.

        Returns:
            Minimum similarity threshold (0.1)
        """
        return 0.1

    def embed(
        self,
        text_chunks: list[str],
        chunk_metadatas: list[dict] | None = None  # noqa: ARG002
    ) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Args:
            text_chunks: List of text chunks to embed
            chunk_metadatas: Optional list of metadata dicts for each chunk (not used by Ollama)

        Returns:
            EmbeddingResult with generated embeddings and metadata
        """
        if not text_chunks:
            return EmbeddingResult(
                embedder_name=self.name,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
            )

        try:
            # Process texts in batches to avoid overwhelming the service
            all_embeddings = []
            for i in range(0, len(text_chunks), self.batch_size):
                batch = text_chunks[i : i + self.batch_size]
                batch_embeddings = self._embed_batch(batch)
                all_embeddings.extend(batch_embeddings)

            return EmbeddingResult(
                embedder_name=self.name,
                embedder_config=self.get_configuration(),
                embeddings=all_embeddings,
                chunk_count=len(all_embeddings),
                indexed_date=datetime.now(),
            )

        except Exception as e:
            # Return failed result with error info
            return EmbeddingResult(
                embedder_name=self.name,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
                error_message=str(e),
            )

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text chunks to embed

        Returns:
            List of embedding vectors

        Raises:
            Exception: If embedding generation fails
        """
        embeddings = []

        for text in texts:
            payload = {"model": self.model, "prompt": text}

            try:
                response = requests.post(
                    self._embeddings_url,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                result = response.json()
                if "embedding" not in result:
                    raise ValueError(f"No embedding in response: {result}")

                embeddings.append(result["embedding"])

            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(
                    f"Cannot connect to Ollama service at {self.base_url}. "
                    f"Make sure Ollama is running."
                ) from e
            except requests.exceptions.Timeout as e:
                raise TimeoutError(
                    f"Ollama request timed out after {self.timeout} seconds"
                ) from e
            except requests.exceptions.HTTPError as e:
                raise ValueError(f"Ollama HTTP error: {e.response.status_code}") from e

        return embeddings

    def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            Exception: If embedding generation fails
        """
        result = self.embed([text])
        if result.embeddings:
            return result.embeddings[0]
        if result.error_message:
            raise RuntimeError(result.error_message)
        raise RuntimeError("Unknown error generating embedding")

    def test_connection(self) -> bool:
        """Test connection to Ollama service.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Test with simple text
            self.embed_single("test")
            return True
        except Exception:
            return False

    def get_embedding_dimension(self) -> int:
        """Return the dimension of generated embeddings.

        Returns:
            Embedding dimension (model-dependent)
        """
        # Different Ollama models have different dimensions
        model_dimensions = {
            "mxbai-embed-large": 1024,
            "nomic-embed-text": 768,
            "all-minilm": 384,
            "snowflake-arctic-embed": 1024,
        }
        return model_dimensions.get(self.model, 768)  # Default to 768

    def get_configuration(self) -> dict[str, Any]:
        """Return embedder configuration.

        Returns:
            Dictionary with configuration information
        """
        return {
            "model_name": self.model,
            "dimension": self.get_embedding_dimension(),
            "max_tokens": 512,  # Typical for most models
            "batch_size": self.batch_size,
            "requires_gpu": False,  # Ollama can run on CPU
            "base_url": self.base_url,
            "timeout": self.timeout,
        }

    def get_capabilities(self) -> dict[str, Any]:
        """Get embedder capabilities and configuration.

        Returns:
            Dictionary describing embedder capabilities
        """
        return {
            "name": self.name,
            "description": f"Ollama embedder using {self.model}",
            "supported_models": [
                "mxbai-embed-large",
                "nomic-embed-text",
                "all-minilm",
                "snowflake-arctic-embed",
            ],
            "features": [
                "batch_processing",
                "configurable_model",
                "local_inference",
                "privacy_preserving",
            ],
            "configuration": self.get_configuration(),
            "limitations": {
                "requires_ollama_service": True,
                "local_only": True,
                "model_dependent_dimensions": True,
            },
        }


# Register the embedder
register_embedder("ollama", OllamaEmbedder)
