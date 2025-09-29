"""Tests for core models."""

from datetime import datetime
from pathlib import Path

from rkb.core.models import (
    ChunkMetadata,
    ChunkResult,
    Document,
    DocumentStatus,
    EmbeddingResult,
    ExperimentConfig,
    ExtractionResult,
    ExtractionStatus,
    SearchResult,
)


class TestDocument:
    """Tests for Document model."""

    def test_document_creation_with_defaults(self):
        """Test creating document with default values."""
        doc = Document()

        assert doc.doc_id is not None
        assert len(doc.doc_id) > 0
        assert doc.status == DocumentStatus.PENDING
        assert doc.version == 1
        assert isinstance(doc.authors, list)
        assert len(doc.authors) == 0
        assert isinstance(doc.added_date, datetime)

    def test_document_with_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        doc = Document(source_path="/test/path.pdf")

        assert isinstance(doc.source_path, Path)
        assert doc.source_path == Path("/test/path.pdf")

    def test_document_with_all_fields(self):
        """Test document creation with all fields."""
        doc = Document(
            source_path=Path("/test/paper.pdf"),
            title="Test Paper",
            authors=["Author One", "Author Two"],
            arxiv_id="2506.06542v1",
            doi="10.1000/test",
            version=2,
        )

        assert doc.title == "Test Paper"
        assert len(doc.authors) == 2
        assert doc.arxiv_id == "2506.06542v1"
        assert doc.version == 2


class TestChunkMetadata:
    """Tests for ChunkMetadata model."""

    def test_chunk_metadata_creation(self):
        """Test creating chunk metadata."""
        metadata = ChunkMetadata(
            chunk_index=0,
            chunk_length=1500,
            has_equations=True,
            display_eq_count=2,
            inline_eq_count=5,
        )

        assert metadata.chunk_index == 0
        assert metadata.chunk_length == 1500
        assert metadata.has_equations is True
        assert metadata.display_eq_count == 2
        assert metadata.inline_eq_count == 5
        assert isinstance(metadata.page_numbers, list)
        assert isinstance(metadata.section_hierarchy, list)


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    def test_extraction_result_defaults(self):
        """Test extraction result with defaults."""
        result = ExtractionResult()

        assert result.extraction_id is not None
        assert result.status == ExtractionStatus.COMPLETE
        assert isinstance(result.chunks, list)
        assert isinstance(result.chunk_metadata, list)
        assert isinstance(result.extraction_date, datetime)

    def test_extraction_result_with_path_conversion(self):
        """Test path string conversion."""
        result = ExtractionResult(extraction_path="/test/output.mmd")

        assert isinstance(result.extraction_path, Path)
        assert result.extraction_path == Path("/test/output.mmd")

    def test_extraction_result_with_chunks(self):
        """Test extraction result with actual chunks."""
        chunks = ["First chunk", "Second chunk", "Third chunk"]
        metadata = [
            ChunkMetadata(0, 100, False, 0, 0),
            ChunkMetadata(1, 150, True, 1, 2),
            ChunkMetadata(2, 120, False, 0, 0),
        ]

        result = ExtractionResult(
            doc_id="test-doc",
            chunks=chunks,
            chunk_metadata=metadata,
            page_count=3,
        )

        assert len(result.chunks) == 3
        assert len(result.chunk_metadata) == 3
        assert result.page_count == 3
        assert result.doc_id == "test-doc"


class TestEmbeddingResult:
    """Tests for EmbeddingResult model."""

    def test_embedding_result_defaults(self):
        """Test embedding result with defaults."""
        result = EmbeddingResult()

        assert result.embedding_id is not None
        assert result.chunk_count == 0
        assert isinstance(result.embeddings, list)
        assert isinstance(result.embedder_config, dict)

    def test_embedding_result_chunk_count_auto_update(self):
        """Test that chunk_count is auto-updated from embeddings."""
        embeddings = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        result = EmbeddingResult(embeddings=embeddings)

        assert result.chunk_count == 2

    def test_embedding_result_path_conversion(self):
        """Test vector DB path conversion."""
        result = EmbeddingResult(vector_db_path="/test/chroma_db")

        assert isinstance(result.vector_db_path, Path)
        assert result.vector_db_path == Path("/test/chroma_db")


class TestChunkResult:
    """Tests for ChunkResult model."""

    def test_chunk_result_creation(self):
        """Test creating a chunk result."""
        result = ChunkResult(
            chunk_id="chunk-1",
            content="Test content",
            similarity=0.7,
            distance=0.3,
        )

        assert result.chunk_id == "chunk-1"
        assert result.content == "Test content"
        assert result.similarity == 0.7
        assert result.distance == 0.3
        assert isinstance(result.metadata, dict)

    def test_chunk_result_with_metadata(self):
        """Test chunk result with metadata."""
        metadata = {"doc_id": "test-doc", "chunk_index": 0, "has_equations": True}
        result = ChunkResult(
            chunk_id="chunk-1",
            content="Mathematical content",
            similarity=0.8,
            distance=0.2,
            metadata=metadata,
        )

        assert result.metadata == metadata
        assert result.metadata["has_equations"] is True


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self):
        """Test creating a search result."""
        result = SearchResult(query="test query")

        assert result.query == "test query"
        assert isinstance(result.chunk_results, list)
        assert len(result.chunk_results) == 0
        assert result.total_results == 0
        assert result.search_time == 0.0
        assert isinstance(result.filters_applied, dict)
        assert result.error_message is None

    def test_search_result_with_chunks(self):
        """Test search result with chunk results."""
        chunk1 = ChunkResult(
            chunk_id="chunk-1",
            content="First result",
            similarity=0.9,
            distance=0.1,
        )
        chunk2 = ChunkResult(
            chunk_id="chunk-2",
            content="Second result",
            similarity=0.8,
            distance=0.2,
        )

        result = SearchResult(
            query="test query",
            chunk_results=[chunk1, chunk2],
            total_results=2,
            search_time=0.15,
            filters_applied={"project_id": "proj-123"},
        )

        assert len(result.chunk_results) == 2
        assert result.chunk_results[0].similarity == 0.9
        assert result.chunk_results[1].similarity == 0.8
        assert result.total_results == 2
        assert result.search_time == 0.15
        assert result.filters_applied["project_id"] == "proj-123"


class TestExperimentConfig:
    """Tests for ExperimentConfig model."""

    def test_experiment_config_defaults(self):
        """Test experiment config with defaults."""
        config = ExperimentConfig()

        assert config.experiment_id is not None
        assert config.chunk_size == 2000
        assert config.search_strategy == "semantic_only"
        assert isinstance(config.embedder_config, dict)

    def test_experiment_config_path_conversion(self):
        """Test vector DB path conversion."""
        config = ExperimentConfig(vector_db_path="/test/experiment_db")

        assert isinstance(config.vector_db_path, Path)
        assert config.vector_db_path == Path("/test/experiment_db")

    def test_experiment_config_full(self):
        """Test experiment config with all fields."""
        config = ExperimentConfig(
            experiment_name="test_experiment",
            project_id="proj-123",
            extractor="nougat",
            embedder="ollama-mxbai",
            chunk_size=1500,
        )

        assert config.experiment_name == "test_experiment"
        assert config.project_id == "proj-123"
        assert config.extractor == "nougat"
        assert config.embedder == "ollama-mxbai"
        assert config.chunk_size == 1500
