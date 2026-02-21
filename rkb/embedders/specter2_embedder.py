"""SPECTER2 embedder using sentence-transformers and explicit Chroma vectors."""

from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.interfaces import EmbedderInterface
from rkb.core.models import EmbeddingResult
from rkb.embedders.base import register_embedder

_SPECTER2_MODEL = "allenai/specter2_base"
_EMBEDDING_DIM = 768


class Specter2Embedder(EmbedderInterface):
    """SPECTER2-based embedder for scientific document retrieval.

    Uses ``allenai/specter2_base`` via sentence-transformers.  Embeddings are
    computed explicitly and stored in Chroma with cosine similarity metric.
    Lazy-loads the model on first use to avoid download cost at import time.
    """

    def __init__(
        self,
        collection_name: str = "documents",
        db_path: Path | str | None = None,
    ) -> None:
        """Initialise the Specter2 embedder.

        Args:
            collection_name: Name for the Chroma collection.
            db_path: Path to the Chroma database directory.
        """
        self.collection_name = collection_name
        self.db_path = Path(db_path) if db_path else Path("rkb_chroma_db")
        self._model = None

    @property
    def name(self) -> str:
        """Return the embedder name."""
        return "specter2"

    @property
    def version(self) -> str:
        """Return the embedder version."""
        return "1.0.0"

    @property
    def minimum_threshold(self) -> float:
        """Minimum similarity threshold.

        SPECTER2 scores are generally higher than MiniLM so we use a higher
        floor of 0.3 (cosine similarity after conversion).
        """
        return 0.3

    def _get_model(self):  # noqa: ANN202
        """Lazy-load and return the SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

            self._model = SentenceTransformer(_SPECTER2_MODEL)
        return self._model

    def embed(
        self,
        text_chunks: list[str],
        chunk_metadatas: list[dict] | None = None,
    ) -> EmbeddingResult:
        """Generate SPECTER2 embeddings and store them in Chroma.

        Args:
            text_chunks: Text chunks to embed.
            chunk_metadatas: Optional metadata dicts for each chunk.

        Returns:
            EmbeddingResult (embeddings list is empty — vectors live in Chroma).
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

            model = self._get_model()

            # Encode all chunks
            vectors = model.encode(text_chunks, show_progress_bar=False)
            embeddings_list: list[list[float]] = [v.tolist() for v in vectors]

            # Set up persistent Chroma client
            self.db_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.db_path))

            # Get or create collection with cosine metric
            try:
                collection = client.get_collection(name=self.collection_name)
            except Exception:
                collection = client.create_collection(
                    name=self.collection_name,
                    metadata={
                        "description": "Academic papers indexed with SPECTER2",
                        "created": datetime.now().isoformat(),
                        "embedding_model": _SPECTER2_MODEL,
                        "hnsw:space": "cosine",
                    },
                )

            # Build IDs and metadata
            chunk_ids = [
                f"chunk_{i}_{datetime.now().timestamp()}" for i in range(len(text_chunks))
            ]

            if chunk_metadatas and len(chunk_metadatas) == len(text_chunks):
                metadatas = []
                for i, meta in enumerate(chunk_metadatas):
                    chunk_meta = dict(meta)
                    chunk_meta["created"] = datetime.now().isoformat()
                    if "chunk_index" not in chunk_meta:
                        chunk_meta["chunk_index"] = i
                    metadatas.append(chunk_meta)
            else:
                metadatas = [
                    {"chunk_index": i, "created": datetime.now().isoformat()}
                    for i in range(len(text_chunks))
                ]

            # Add with explicit embeddings so Chroma does not re-embed
            collection.add(
                embeddings=embeddings_list,
                documents=text_chunks,
                ids=chunk_ids,
                metadatas=metadatas,
            )

            return EmbeddingResult(
                embedder_name=self.name,
                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],  # Stored in Chroma; not returned in-memory
                chunk_count=len(text_chunks),
                indexed_date=datetime.now(),
            )

        except ImportError as exc:
            return EmbeddingResult(
                embedder_name=self.name,
                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
                error_message=f"Required package not installed: {exc}",
            )
        except Exception as exc:
            return EmbeddingResult(
                embedder_name=self.name,
                vector_db_path=self.db_path,
                embedder_config=self.get_configuration(),
                embeddings=[],
                chunk_count=0,
                error_message=str(exc),
            )

    def embed_query(self, query: str) -> list[float] | None:
        """Embed a single query string using SPECTER2.

        Args:
            query: Query text.

        Returns:
            Embedding vector as a list of floats.
        """
        model = self._get_model()
        vector = model.encode([query], show_progress_bar=False)[0]
        return vector.tolist()

    def get_embedding_dimension(self) -> int:
        """Return embedding dimension (768 for SPECTER2)."""
        return _EMBEDDING_DIM

    def get_configuration(self) -> dict[str, Any]:
        """Return embedder configuration."""
        return {
            "model_name": _SPECTER2_MODEL,
            "dimension": _EMBEDDING_DIM,
            "max_tokens": 512,
            "batch_size": 32,
            "requires_gpu": False,
            "collection_name": self.collection_name,
            "db_path": str(self.db_path),
            "distance_metric": "cosine",
        }

    def get_capabilities(self) -> dict[str, Any]:
        """Return embedder capabilities."""
        return {
            "name": self.name,
            "description": "SPECTER2 embedder tuned for scientific documents",
            "supported_models": [_SPECTER2_MODEL],
            "features": [
                "scientific_domain",
                "persistent_storage",
                "explicit_embeddings",
                "cosine_metric",
                "query_embedding",
            ],
            "configuration": self.get_configuration(),
        }


# Register the embedder
register_embedder("specter2", Specter2Embedder)
