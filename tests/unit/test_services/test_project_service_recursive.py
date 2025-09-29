"""Tests for ProjectService recursive PDF finding."""

import tempfile
from pathlib import Path

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.services.project_service import ProjectService


class TestProjectServiceRecursive:
    """Test recursive PDF finding for Zotero-style directory structures."""

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

            # Also create a PDF in the root (should also be found)
            (storage_dir / "root_paper.pdf").write_bytes(b"PDF content 4")

            yield storage_dir

    def test_find_recent_pdfs_recursive(self, temp_registry, zotero_structure):
        """Test that find_recent_pdfs finds PDFs in subdirectories."""
        service = ProjectService(temp_registry)

        # Find PDFs in the Zotero-like structure
        files = service.find_recent_pdfs(
            data_dir=zotero_structure,
            num_files=10
        )

        # Should find all 4 PDFs
        assert len(files) == 4

        # Check that files from subdirectories are found
        file_names = [f["name"] for f in files]
        assert "Document.pdf" in file_names  # Should find at least one
        assert "Paper.pdf" in file_names
        assert "root_paper.pdf" in file_names

        # Check that paths include subdirectory structure
        file_paths = [f["path"] for f in files]
        subdirectory_files = [
            p for p in file_paths
            if "/ABC123/" in p or "/XYZ789/" in p or "/DEF456/" in p
        ]
        assert len(subdirectory_files) == 3  # Three files in subdirectories

    def test_find_recent_pdfs_empty_subdirectories(self, temp_registry):
        """Test behavior when subdirectories exist but contain no PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create empty subdirectories
            (base_dir / "empty1").mkdir()
            (base_dir / "empty2").mkdir()
            (base_dir / "empty2" / "nested").mkdir()

            service = ProjectService(temp_registry)

            # Should raise FileNotFoundError when no PDFs found
            with pytest.raises(FileNotFoundError, match="No PDF files found"):
                service.find_recent_pdfs(data_dir=base_dir, num_files=10)

    def test_find_recent_pdfs_mixed_file_types(self, temp_registry, zotero_structure):
        """Test that only PDF files are found, ignoring other file types."""
        # Add some non-PDF files
        (zotero_structure / "ABC123" / "notes.txt").write_text("Notes")
        (zotero_structure / "XYZ789" / "image.jpg").write_bytes(b"Image data")
        (zotero_structure / "DEF456" / "data.csv").write_text("csv,data")

        service = ProjectService(temp_registry)

        files = service.find_recent_pdfs(
            data_dir=zotero_structure,
            num_files=10
        )

        # Should still only find the 4 PDFs, not the other files
        assert len(files) == 4

        # All found files should be PDFs
        for file_info in files:
            assert file_info["name"].endswith(".pdf")

    def test_find_recent_pdfs_deep_nesting(self, temp_registry):
        """Test finding PDFs in deeply nested directory structures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create deeply nested structure
            deep_path = base_dir / "level1" / "level2" / "level3" / "level4"
            deep_path.mkdir(parents=True)
            (deep_path / "deep_paper.pdf").write_bytes(b"Deep PDF content")

            service = ProjectService(temp_registry)

            files = service.find_recent_pdfs(
                data_dir=base_dir,
                num_files=10
            )

            # Should find the deeply nested PDF
            assert len(files) == 1
            assert files[0]["name"] == "deep_paper.pdf"
            assert "level1/level2/level3/level4" in files[0]["path"]
