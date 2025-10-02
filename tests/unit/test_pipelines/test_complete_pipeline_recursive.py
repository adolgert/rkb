"""Tests for CompletePipeline recursive PDF finding."""

import tempfile
from pathlib import Path

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.pipelines.complete_pipeline import CompletePipeline


class TestCompletePipelineRecursive:
    """Test recursive PDF finding in CompletePipeline."""

    @pytest.fixture
    def temp_registry(self):
        """Create a temporary document registry."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def zotero_structure(self):
        """Create a Zotero-like directory structure with PDFs in subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create Zotero-like structure
            storage_dir = base_dir / "storage"

            # Create multiple subdirectories with PDFs
            (storage_dir / "ABC123").mkdir(parents=True)
            (storage_dir / "ABC123" / "Document.pdf").write_bytes(b"PDF content 1")

            (storage_dir / "XYZ789").mkdir(parents=True)
            (storage_dir / "XYZ789" / "Document.pdf").write_bytes(b"PDF content 2")

            (storage_dir / "DEF456").mkdir(parents=True)
            (storage_dir / "DEF456" / "Paper.pdf").write_bytes(b"PDF content 3")

            yield storage_dir

    def test_find_recent_pdfs_recursive(self, temp_registry, zotero_structure):
        """Test that CompletePipeline.find_recent_pdfs finds PDFs in subdirectories."""
        pipeline = CompletePipeline(
            registry=temp_registry,
            extractor_name="nougat",
            embedder_name="chroma",
        )

        # Find PDFs in the Zotero-like structure
        files = pipeline.find_recent_pdfs(
            data_dir=zotero_structure,
            num_files=10
        )

        # Should find all 3 PDFs
        assert len(files) == 3

        # Check that files from subdirectories are found
        file_names = [f["name"] for f in files]
        assert "Document.pdf" in file_names  # Should find at least one
        assert "Paper.pdf" in file_names

        # Check that paths include subdirectory structure
        file_paths = [f["path"] for f in files]
        subdirectory_files = [
            p for p in file_paths
            if "/ABC123/" in p or "/XYZ789/" in p or "/DEF456/" in p
        ]
        assert len(subdirectory_files) == 3  # All files in subdirectories

    def test_find_recent_pdfs_empty_subdirectories(self, temp_registry):
        """Test behavior when subdirectories exist but contain no PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create empty subdirectories
            (base_dir / "empty1").mkdir()
            (base_dir / "empty2").mkdir()
            (base_dir / "empty2" / "nested").mkdir()

            pipeline = CompletePipeline(
                registry=temp_registry,
                extractor_name="nougat",
                embedder_name="chroma",
            )

            # Should raise FileNotFoundError when no PDFs found
            with pytest.raises(FileNotFoundError, match="No PDF files found"):
                pipeline.find_recent_pdfs(data_dir=base_dir, num_files=10)
