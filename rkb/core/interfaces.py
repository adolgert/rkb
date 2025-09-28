"""Abstract interfaces for the RKB system."""

from abc import ABC, abstractmethod
from pathlib import Path

from rkb.core.models import EmbeddingResult, ExtractionResult


class ExtractorInterface(ABC):
    """Abstract interface for document extractors."""

    @abstractmethod
    def extract(self, source_path: Path) -> ExtractionResult:
        """Extract text content from a document.

        Args:
            source_path: Path to the source document (PDF, LaTeX, etc.)

        Returns:
            ExtractionResult containing extracted text and metadata

        Raises:
            FileNotFoundError: If source file doesn't exist
            ExtractionError: If extraction fails
        """

    @abstractmethod
    def get_capabilities(self) -> dict[str, any]:
        """Return extractor capabilities and configuration.

        Returns:
            Dictionary with capability information:
            - handles_math: bool - supports mathematical equations
            - handles_tables: bool - supports table extraction
            - handles_figures: bool - supports figure extraction
            - input_formats: list[str] - supported file formats
            - speed: str - relative speed (fast/medium/slow)
            - quality: str - relative quality (high/medium/low)
            - max_pages: int|None - maximum pages supported
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the extractor name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the extractor version."""


class EmbedderInterface(ABC):
    """Abstract interface for text embedders."""

    @abstractmethod
    def embed(self, text_chunks: list[str]) -> EmbeddingResult:
        """Generate embeddings for text chunks.

        Args:
            text_chunks: List of text chunks to embed

        Returns:
            EmbeddingResult containing embeddings and metadata

        Raises:
            EmbeddingError: If embedding generation fails
        """

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return the dimension of generated embeddings."""

    @abstractmethod
    def get_configuration(self) -> dict[str, any]:
        """Return embedder configuration.

        Returns:
            Dictionary with configuration information:
            - model_name: str - name of the embedding model
            - dimension: int - embedding dimension
            - max_tokens: int - maximum tokens per chunk
            - batch_size: int - optimal batch size
            - requires_gpu: bool - whether GPU is required
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the embedder name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the embedder version."""


class ChunkerInterface(ABC):
    """Abstract interface for text chunkers."""

    @abstractmethod
    def chunk_text(self, text: str, max_chunk_size: int = 2000) -> list[str]:
        """Split text into chunks.

        Args:
            text: Text to split
            max_chunk_size: Maximum size per chunk in characters

        Returns:
            List of text chunks
        """

    @abstractmethod
    def get_chunk_metadata(self, chunks: list[str]) -> list[dict]:
        """Extract metadata for each chunk.

        Args:
            chunks: List of text chunks

        Returns:
            List of metadata dictionaries for each chunk
        """


class VectorDatabaseInterface(ABC):
    """Abstract interface for vector databases."""

    @abstractmethod
    def create_collection(self, name: str, dimension: int) -> None:
        """Create a new collection.

        Args:
            name: Collection name
            dimension: Vector dimension
        """

    @abstractmethod
    def add_vectors(
        self,
        collection: str,
        vectors: list[list[float]],
        documents: list[str],
        metadata: list[dict],
        ids: list[str],
    ) -> None:
        """Add vectors to a collection.

        Args:
            collection: Collection name
            vectors: List of embedding vectors
            documents: List of document texts
            metadata: List of metadata dictionaries
            ids: List of unique identifiers
        """

    @abstractmethod
    def search(
        self,
        collection: str,
        query_vector: list[float],
        n_results: int = 5,
        where: dict | None = None,
    ) -> dict:
        """Search for similar vectors.

        Args:
            collection: Collection name
            query_vector: Query embedding
            n_results: Number of results to return
            where: Optional metadata filter

        Returns:
            Search results dictionary
        """

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Delete a collection.

        Args:
            name: Collection name
        """
