"""Core data models for the RKB system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class DocumentStatus(Enum):
    """Document processing status."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class ExtractionStatus(Enum):
    """Extraction processing status."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class Document:
    """Represents a document in the system."""

    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_path: Path | None = None
    content_hash: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    arxiv_id: str | None = None
    doi: str | None = None
    added_date: datetime = field(default_factory=datetime.now)
    updated_date: datetime = field(default_factory=datetime.now)
    version: int = 1
    parent_doc_id: str | None = None
    status: DocumentStatus = DocumentStatus.PENDING

    def __post_init__(self) -> None:
        """Convert string paths to Path objects."""
        if isinstance(self.source_path, str):
            self.source_path = Path(self.source_path)


@dataclass
class ChunkMetadata:
    """Metadata for a text chunk."""

    chunk_index: int
    chunk_length: int
    has_equations: bool
    display_eq_count: int
    inline_eq_count: int
    page_numbers: list[int] = field(default_factory=list)
    section_hierarchy: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result from document extraction."""

    extraction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    extraction_path: Path | None = None
    content: str | None = None
    chunks: list[str] = field(default_factory=list)
    chunk_metadata: list[ChunkMetadata] = field(default_factory=list)
    extraction_date: datetime = field(default_factory=datetime.now)
    quality_score: float | None = None
    page_count: int | None = None
    status: ExtractionStatus = ExtractionStatus.COMPLETE
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Convert string paths to Path objects."""
        if isinstance(self.extraction_path, str):
            self.extraction_path = Path(self.extraction_path)


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embedding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str | None = None
    extraction_id: str | None = None
    embedder_name: str | None = None
    embedder_config: dict = field(default_factory=dict)
    embeddings: list[list[float]] = field(default_factory=list)
    chunk_count: int = 0
    vector_db_path: Path | None = None
    indexed_date: datetime = field(default_factory=datetime.now)
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Convert string paths to Path objects and update chunk count."""
        if isinstance(self.vector_db_path, str):
            self.vector_db_path = Path(self.vector_db_path)
        if not self.chunk_count and self.embeddings:
            self.chunk_count = len(self.embeddings)


@dataclass
class SearchResult:
    """Single search result."""

    doc_id: str
    chunk_index: int
    content: str
    distance: float
    similarity: float = field(init=False)
    metadata: ChunkMetadata | None = None
    document: Document | None = None

    def __post_init__(self) -> None:
        """Calculate similarity from distance."""
        self.similarity = 1 - self.distance if self.distance is not None else 0.0


@dataclass
class DocumentResult:
    """Document-level search result (aggregated from chunks)."""

    document: Document
    best_score: float
    chunk_results: list[SearchResult]
    total_chunks: int

    @property
    def avg_score(self) -> float:
        """Average score across all chunks."""
        if not self.chunk_results:
            return 0.0
        return sum(r.similarity for r in self.chunk_results) / len(self.chunk_results)


@dataclass
class ComparisonResult:
    """Result from comparing multiple experiments."""

    query: str
    experiment_results: dict[str, list[SearchResult]]
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProjectStats:
    """Statistics for a project."""

    project_id: str
    document_count: int
    extracted_count: int
    indexed_count: int
    failed_count: int
    total_chunks: int
    available_experiments: list[str] = field(default_factory=list)


@dataclass
class ExperimentConfig:
    """Configuration for an experiment."""

    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str | None = None
    experiment_name: str | None = None
    extractor: str | None = None
    embedder: str | None = None
    embedder_config: dict = field(default_factory=dict)
    chunk_size: int = 2000
    search_strategy: str = "semantic_only"
    vector_db_path: Path | None = None
    created_date: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Convert string paths to Path objects."""
        if isinstance(self.vector_db_path, str):
            self.vector_db_path = Path(self.vector_db_path)
