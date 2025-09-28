"""Chroma-based embedder using Chroma's default embedding model."""

from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.interfaces import EmbedderInterface
from rkb.core.models import EmbeddingResult
from rkb.embedders.base import register_embedder


class ChromaEmbedder(EmbedderInterface):
    """Chroma-based embedder using Chroma's default embedding model."""

    def __init__(
        self,
        collection_name: str = "documents",
        db_path: Path | str | None = None,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        """Initialize Chroma embedder.

        Args:
            collection_name: Name for the Chroma collection
            db_path: Path to Chroma database directory
            model_name: Chroma embedding model name
        """
        self.collection_name = collection_name
        self.db_path = Path(db_path) if db_path else Path("rkb_chroma_db")
        self.model_name = model_name

    @property
    def name(self) -> str:
        """Return the embedder name."""
        return "chroma"

    @property
    def version(self) -> str:
        """Return the embedder version."""
        return "1.0.0"

    def embed(self, text_chunks: list[str]) -> EmbeddingResult:
        """Generate embeddings using Chroma's default model.

        Args:
            text_chunks: List of text chunks to embed

        Returns:
            EmbeddingResult with generated embeddings and metadata
        """
        if not text_chunks:
            return EmbeddingResult(
                embedder_name=self.name,
                                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
            )

        try:
            import chromadb

            # Use default db path
            self.db_path.mkdir(parents=True, exist_ok=True)

            # Create Chroma client
            client = chromadb.PersistentClient(path=str(self.db_path))

            # Get or create collection
            try:
                collection = client.get_collection(name=self.collection_name)
            except chromadb.errors.NotFoundError:
                # Collection doesn't exist, create it
                collection = client.create_collection(
                    name=self.collection_name,
                    metadata={
                        "description": "Academic papers with equation-aware search",
                        "created": datetime.now().isoformat(),
                        "embedding_model": f"chroma_default_{self.model_name}",
                    },
                )

            # Generate embeddings by adding documents to collection
            # ChromaDB handles embeddings internally - we don't need to extract them
            chunk_ids = [f"chunk_{i}_{datetime.now().timestamp()}" for i in range(len(text_chunks))]

            # Add documents to collection (ChromaDB generates and stores embeddings internally)
            collection.add(
                documents=text_chunks,
                ids=chunk_ids,
                metadatas=[{"chunk_index": i, "created": datetime.now().isoformat()}
                          for i in range(len(text_chunks))],
            )

            # Return result without extracting embeddings (ChromaDB stores them internally)
            return EmbeddingResult(
                embedder_name=self.name,
                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],  # Empty list - embeddings stored in ChromaDB
                chunk_count=len(text_chunks),
                indexed_date=datetime.now(),
            )

        except ImportError as e:
            return EmbeddingResult(
                embedder_name=self.name,
                                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
                error_message=f"ChromaDB not installed: {e}",
            )
        except Exception as e:
            return EmbeddingResult(
                embedder_name=self.name,
                                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
                error_message=str(e),
            )

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
        """Test Chroma availability.

        Returns:
            True if Chroma is available, False otherwise
        """
        try:
            import chromadb

            # Test creating a client
            test_path = self.db_path / "test"
            test_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(test_path))

            # Test creating a temporary collection
            test_collection = f"test_{datetime.now().timestamp()}"
            client.create_collection(name=test_collection)
            client.delete_collection(name=test_collection)

            # Clean up
            if test_path.exists():
                import shutil

                shutil.rmtree(test_path)

            return True
        except Exception:
            return False

    def get_embedding_dimension(self) -> int:
        """Return the dimension of generated embeddings.

        Returns:
            Embedding dimension (model-dependent)
        """
        # Common Chroma model dimensions
        model_dimensions = {
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "multi-qa-MiniLM-L6-cos-v1": 384,
        }
        return model_dimensions.get(self.model_name, 384)  # Default to 384

    def get_configuration(self) -> dict[str, Any]:
        """Return embedder configuration.

        Returns:
            Dictionary with configuration information
        """
        return {
            "model_name": self.model_name,
            "dimension": self.get_embedding_dimension(),
            "max_tokens": 512,  # Typical for sentence transformers
            "batch_size": 100,  # Chroma handles batching internally
            "requires_gpu": False,  # Most models can run on CPU
            "collection_name": self.collection_name,
            "db_path": str(self.db_path),
        }

    def get_capabilities(self) -> dict[str, Any]:
        """Get embedder capabilities and configuration.

        Returns:
            Dictionary describing embedder capabilities
        """
        return {
            "name": self.name,
            "description": f"Chroma embedder using {self.model_name}",
            "supported_models": [
                "all-MiniLM-L6-v2",
                "all-mpnet-base-v2",
                "multi-qa-MiniLM-L6-cos-v1",
            ],
            "features": [
                "persistent_storage",
                "collection_management",
                "metadata_support",
                "automatic_indexing",
            ],
            "configuration": self.get_configuration(),
            "limitations": {
                "requires_chromadb": True,
                "file_system_storage": True,
                "temporary_document_creation": True,
            },
        }


# Register the embedder
register_embedder("chroma", ChromaEmbedder)
