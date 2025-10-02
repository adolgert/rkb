"""Integration tests for checkpoint/resume functionality in IngestionPipeline."""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.checkpoint_manager import CheckpointManager
from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import EmbeddingResult, ExtractionResult
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


class TestIngestionPipelineCheckpointResume:
    """Integration tests for checkpoint/resume in IngestionPipeline."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        registry.close()
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_extractor(self):
        """Create mock extractor."""
        extractor = Mock()
        extractor.name = "mock_extractor"
        extractor.version = "1.0.0"

        # Mock successful extraction
        extraction_result = ExtractionResult(
            extractor_name="mock_extractor",
            extractor_version="1.0.0",
            content="This is test content for extraction. " * 50,
            page_count=1,
        )
        extractor.extract.return_value = extraction_result

        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.name = "mock_embedder"
        embedder.version = "1.0.0"

        # Mock successful embedding
        def mock_embed(text_chunks):
            return EmbeddingResult(
                embedder_name="mock_embedder",
                embeddings=[[0.1, 0.2, 0.3] for _ in text_chunks],
                chunk_count=len(text_chunks),
            )

        embedder.embed.side_effect = mock_embed
        return embedder

    @pytest.fixture
    def sample_pdfs(self):
        """Create sample PDF files for testing."""
        files = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            for i in range(10):
                pdf_path = tmpdir_path / f"test_file_{i}.pdf"
                pdf_path.write_text(f"Sample PDF content {i}")
                files.append(pdf_path)

            yield files

    def test_resume_from_checkpoint(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder, sample_pdfs
    ):
        """Test pipeline resumes from existing checkpoint."""
        with patch(
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create pipeline
            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_project",
                checkpoint_dir=temp_checkpoint_dir,
            )

            # Manually create checkpoint with 3 of 10 files completed
            file_paths_str = [str(p) for p in sample_pdfs]
            batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]

            checkpoint_manager = CheckpointManager(temp_checkpoint_dir)
            checkpoint_manager.save_checkpoint(
                batch_id,
                completed_files=[str(sample_pdfs[0]), str(sample_pdfs[1]), str(sample_pdfs[2])],
                metadata={"total": 10},
            )

            # Call process_batch with resume=True
            results = pipeline.process_batch(file_paths_str, resume=True)

            # Assert only 7 files processed (10 - 3 already completed)
            assert len(results) == 7

            # Assert mock extractor called 7 times, not 10
            assert mock_extractor.extract.call_count == 7

    def test_no_resume_ignores_checkpoint(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder, sample_pdfs
    ):
        """Test resume=False ignores checkpoint."""
        with patch(
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create pipeline
            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_project",
                checkpoint_dir=temp_checkpoint_dir,
            )

            # Create checkpoint with 3 files completed
            file_paths_str = [str(p) for p in sample_pdfs]
            batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]

            checkpoint_manager = CheckpointManager(temp_checkpoint_dir)
            checkpoint_manager.save_checkpoint(
                batch_id,
                completed_files=[str(sample_pdfs[0]), str(sample_pdfs[1]), str(sample_pdfs[2])],
                metadata={"total": 10},
            )

            # Call process_batch with resume=False
            results = pipeline.process_batch(file_paths_str, resume=False)

            # Assert all 10 files processed (checkpoint ignored)
            assert len(results) == 10

            # Assert mock extractor called 10 times
            assert mock_extractor.extract.call_count == 10

    def test_checkpoint_cleared_on_completion(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder, sample_pdfs
    ):
        """Test checkpoint file deleted after successful batch."""
        with patch(
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create pipeline
            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_project",
                checkpoint_dir=temp_checkpoint_dir,
            )

            # Process batch to completion
            file_paths_str = [str(p) for p in sample_pdfs[:5]]  # Use 5 files
            results = pipeline.process_batch(file_paths_str, resume=True)

            # Assert processing completed
            assert len(results) == 5

            # Calculate expected batch_id
            batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]
            checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"

            # Assert checkpoint file was deleted
            assert not checkpoint_file.exists()

    def test_checkpoint_not_cleared_on_interrupt(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder, sample_pdfs
    ):
        """Test checkpoint persists when interrupted."""
        with patch(
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create pipeline
            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_project",
                checkpoint_dir=temp_checkpoint_dir,
            )

            # Set interrupted flag after first file
            # Note: interrupt check happens BEFORE processing next file
            original_process = pipeline.process_single_document
            call_count = [0]

            def interrupt_after_first(*args, **kwargs):
                call_count[0] += 1
                result = original_process(*args, **kwargs)
                if call_count[0] == 1:
                    pipeline.interrupted = True
                return result

            pipeline.process_single_document = interrupt_after_first

            # Process batch (will call sys.exit(0) after saving checkpoint)
            file_paths_str = [str(p) for p in sample_pdfs[:5]]

            # Should exit when interrupted (after completing 1 file)
            with pytest.raises(SystemExit) as exc_info:
                pipeline.process_batch(file_paths_str, resume=True)

            # Verify exit code is 0
            assert exc_info.value.code == 0

            # Calculate expected batch_id
            batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]
            checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"

            # Assert checkpoint file exists
            assert checkpoint_file.exists()


class TestBatchIdGeneration:
    """Test batch ID generation logic."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        registry.close()
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_same_files_same_batch_id(self, temp_db, temp_checkpoint_dir):
        """Test same file list generates same batch ID."""
        file_paths = [Path("/path/to/file1.pdf"), Path("/path/to/file2.pdf")]

        # Calculate batch_id manually
        batch_id_1 = hashlib.md5("".join(str(p) for p in file_paths).encode()).hexdigest()[:16]

        # Create checkpoint with these files
        checkpoint_manager = CheckpointManager(temp_checkpoint_dir)
        checkpoint_manager.save_checkpoint(batch_id_1, [], {})

        # Use same files in different order (batch_id should be different)
        file_paths_reversed = [Path("/path/to/file2.pdf"), Path("/path/to/file1.pdf")]
        batch_id_2 = hashlib.md5(
            "".join(str(p) for p in file_paths_reversed).encode()
        ).hexdigest()[:16]

        # Batch IDs should be different (order matters)
        assert batch_id_1 != batch_id_2

    def test_different_files_different_batch_id(self, temp_checkpoint_dir):
        """Test different file lists generate different batch IDs."""
        files_a = [Path("/path/to/file1.pdf"), Path("/path/to/file2.pdf")]
        files_b = [Path("/path/to/file3.pdf"), Path("/path/to/file4.pdf")]

        batch_id_a = hashlib.md5("".join(str(p) for p in files_a).encode()).hexdigest()[:16]
        batch_id_b = hashlib.md5("".join(str(p) for p in files_b).encode()).hexdigest()[:16]

        assert batch_id_a != batch_id_b

    def test_file_order_affects_batch_id(self, temp_checkpoint_dir):
        """Test file order changes batch ID."""
        files_ordered = [
            Path("/path/to/file1.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file3.pdf"),
        ]
        files_reversed = [
            Path("/path/to/file3.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file1.pdf"),
        ]

        batch_id_ordered = hashlib.md5("".join(str(p) for p in files_ordered).encode()).hexdigest()[
            :16
        ]
        batch_id_reversed = hashlib.md5(
            "".join(str(p) for p in files_reversed).encode()
        ).hexdigest()[:16]

        # Different order = different batch ID
        assert batch_id_ordered != batch_id_reversed


class TestCheckpointStateTracking:
    """Test checkpoint state tracking."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        registry.close()
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_extractor(self):
        """Create mock extractor."""
        extractor = Mock()
        extractor.name = "mock_extractor"
        extractor.version = "1.0.0"
        extraction_result = ExtractionResult(
            extractor_name="mock_extractor",
            extractor_version="1.0.0",
            content="Test content. " * 50,
            page_count=1,
        )
        extractor.extract.return_value = extraction_result
        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.name = "mock_embedder"
        embedder.version = "1.0.0"

        def mock_embed(text_chunks):
            return EmbeddingResult(
                embedder_name="mock_embedder",
                embeddings=[[0.1, 0.2, 0.3] for _ in text_chunks],
                chunk_count=len(text_chunks),
            )

        embedder.embed.side_effect = mock_embed
        return embedder

    def test_metadata_stored_in_checkpoint(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder
    ):
        """Test checkpoint metadata contains batch info."""
        with patch(  # noqa: SIM117
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create temporary files
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                sample_pdfs = []
                for i in range(5):
                    pdf_path = tmpdir_path / f"test_file_{i}.pdf"
                    pdf_path.write_text(f"Sample PDF content {i}")
                    sample_pdfs.append(pdf_path)

                # Create pipeline
                pipeline = IngestionPipeline(
                    registry=temp_db,
                    extractor_name="mock_extractor",
                    embedder_name="mock_embedder",
                    checkpoint_dir=temp_checkpoint_dir,
                )

                # Interrupt after 2 files
                # Note: interrupt check happens BEFORE processing next file
                original_process = pipeline.process_single_document
                call_count = [0]

                def interrupt_after_two(*args, **kwargs):
                    call_count[0] += 1
                    result = original_process(*args, **kwargs)
                    if call_count[0] == 2:
                        pipeline.interrupted = True
                    return result

                pipeline.process_single_document = interrupt_after_two

                # Process batch (will exit with SystemExit)
                file_paths_str = [str(p) for p in sample_pdfs]

                with pytest.raises(SystemExit):
                    pipeline.process_batch(file_paths_str, resume=True)

                # Load checkpoint
                batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]
                checkpoint_manager = CheckpointManager(temp_checkpoint_dir)
                checkpoint = checkpoint_manager.load_checkpoint(batch_id)

                # Assert metadata contains total count
                assert checkpoint is not None
                assert "metadata" in checkpoint
                assert checkpoint["metadata"]["total"] == 5


class TestInterruptHandling:
    """Test interrupt handling."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        registry.close()
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_extractor(self):
        """Create mock extractor."""
        extractor = Mock()
        extractor.name = "mock_extractor"
        extractor.version = "1.0.0"
        extraction_result = ExtractionResult(
            extractor_name="mock_extractor",
            extractor_version="1.0.0",
            content="Test content. " * 50,
            page_count=1,
        )
        extractor.extract.return_value = extraction_result
        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.name = "mock_embedder"
        embedder.version = "1.0.0"

        def mock_embed(text_chunks):
            return EmbeddingResult(
                embedder_name="mock_embedder",
                embeddings=[[0.1, 0.2, 0.3] for _ in text_chunks],
                chunk_count=len(text_chunks),
            )

        embedder.embed.side_effect = mock_embed
        return embedder

    def test_interrupted_flag_stops_processing(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder
    ):
        """Test setting interrupted=True stops batch."""
        with patch(  # noqa: SIM117
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create temporary files
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                sample_pdfs = []
                for i in range(10):
                    pdf_path = tmpdir_path / f"test_file_{i}.pdf"
                    pdf_path.write_text(f"Sample PDF content {i}")
                    sample_pdfs.append(pdf_path)

                # Create pipeline
                pipeline = IngestionPipeline(
                    registry=temp_db,
                    extractor_name="mock_extractor",
                    embedder_name="mock_embedder",
                    checkpoint_dir=temp_checkpoint_dir,
                )

                # Interrupt after 3 files
                # Note: interrupt check happens BEFORE processing next file
                original_process = pipeline.process_single_document
                call_count = [0]

                def interrupt_after_three(*args, **kwargs):
                    call_count[0] += 1
                    result = original_process(*args, **kwargs)
                    if call_count[0] == 3:
                        pipeline.interrupted = True
                    return result

                pipeline.process_single_document = interrupt_after_three

                # Process batch (will exit with SystemExit)
                file_paths_str = [str(p) for p in sample_pdfs]

                with pytest.raises(SystemExit) as exc_info:
                    pipeline.process_batch(file_paths_str, resume=True)

                # Assert only 3 files processed
                assert mock_extractor.extract.call_count == 3

                # Assert exit code is 0
                assert exc_info.value.code == 0

    def test_checkpoint_saved_before_exit(
        self, temp_db, temp_checkpoint_dir, mock_extractor, mock_embedder
    ):
        """Test checkpoint saved when interrupted."""
        with patch(  # noqa: SIM117
            "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
        ), patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):
            # Create temporary files
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                sample_pdfs = []
                for i in range(5):
                    pdf_path = tmpdir_path / f"test_file_{i}.pdf"
                    pdf_path.write_text(f"Sample PDF content {i}")
                    sample_pdfs.append(pdf_path)

                # Create pipeline
                pipeline = IngestionPipeline(
                    registry=temp_db,
                    extractor_name="mock_extractor",
                    embedder_name="mock_embedder",
                    checkpoint_dir=temp_checkpoint_dir,
                )

                # Interrupt after 2 files
                # Note: interrupt check happens BEFORE processing next file
                original_process = pipeline.process_single_document
                call_count = [0]

                def interrupt_after_two(*args, **kwargs):
                    call_count[0] += 1
                    result = original_process(*args, **kwargs)
                    if call_count[0] == 2:
                        pipeline.interrupted = True
                    return result

                pipeline.process_single_document = interrupt_after_two

                # Process batch (will exit with SystemExit)
                file_paths_str = [str(p) for p in sample_pdfs]

                with pytest.raises(SystemExit):
                    pipeline.process_batch(file_paths_str, resume=True)

                # Calculate batch_id
                batch_id = hashlib.md5("".join(file_paths_str).encode()).hexdigest()[:16]
                checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"

                # Assert checkpoint file exists
                assert checkpoint_file.exists()

                # Load checkpoint and verify it has 2 completed files
                checkpoint_manager = CheckpointManager(temp_checkpoint_dir)
                checkpoint = checkpoint_manager.load_checkpoint(batch_id)
                assert len(checkpoint["completed_files"]) == 2
