"""Tests for project service functionality."""

import tempfile
from pathlib import Path

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document, DocumentStatus
from rkb.services.project_service import ProjectService


class TestProjectService:
    """Tests for ProjectService."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory with sample PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()

            # Create sample PDF files
            for i in range(3):
                pdf_file = data_dir / f"sample_{i}.pdf"
                pdf_file.write_bytes(b"Sample PDF content " + str(i).encode())

            yield data_dir

    def test_initialization(self, temp_db):
        """Test ProjectService initialization."""
        service = ProjectService(registry=temp_db)
        assert service.registry == temp_db

    def test_create_project(self, temp_db):
        """Test creating a new project."""
        service = ProjectService(registry=temp_db)

        project_id = service.create_project(
            project_name="Test Project",
            description="A test project",
            data_dir="/path/to/data",
        )

        assert project_id.startswith("project_")
        assert len(project_id) > 8

    def test_get_project_documents(self, temp_db):
        """Test getting documents for a project."""
        service = ProjectService(registry=temp_db)

        # Add some test documents
        doc1 = Document(source_path=Path("/test1.pdf"), status=DocumentStatus.INDEXED)
        doc1.project_id = "test_project"
        doc2 = Document(source_path=Path("/test2.pdf"), status=DocumentStatus.PENDING)
        doc2.project_id = "test_project"
        doc3 = Document(source_path=Path("/test3.pdf"), status=DocumentStatus.INDEXED)
        doc3.project_id = "other_project"

        temp_db.add_document(doc1)
        temp_db.add_document(doc2)
        temp_db.add_document(doc3)

        # Get all documents for test_project
        docs = service.get_project_documents("test_project")
        assert len(docs) == 2

        # Get indexed documents for test_project
        indexed_docs = service.get_project_documents("test_project", DocumentStatus.INDEXED)
        assert len(indexed_docs) == 1
        assert indexed_docs[0].status == DocumentStatus.INDEXED

    def test_find_recent_pdfs(self, temp_db, temp_data_dir):
        """Test finding recent PDF files."""
        service = ProjectService(registry=temp_db)

        files = service.find_recent_pdfs(
            data_dir=temp_data_dir,
            num_files=2,
            project_id="test_project",
        )

        assert len(files) == 2  # Limited by num_files
        assert all(f["name"].endswith(".pdf") for f in files)
        assert all("path" in f for f in files)
        assert all("size_mb" in f for f in files)
        assert all("modified_date" in f for f in files)
        assert all(f["project_id"] == "test_project" for f in files)

        # Files should be sorted by modification time (most recent first)
        assert files[0]["modified_time"] >= files[1]["modified_time"]

    def test_find_recent_pdfs_with_output_file(self, temp_db, temp_data_dir):
        """Test finding PDFs with output file."""
        service = ProjectService(registry=temp_db)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            files = service.find_recent_pdfs(
                data_dir=temp_data_dir,
                num_files=3,
                output_file=output_file,
            )

            # Check that output file was created
            assert output_file.exists()

            # Verify content
            import json
            with output_file.open() as f:
                saved_files = json.load(f)

            assert len(saved_files) == 3
            assert saved_files == files

        finally:
            if output_file.exists():
                output_file.unlink()

    def test_find_recent_pdfs_no_directory(self, temp_db):
        """Test finding PDFs when directory doesn't exist."""
        service = ProjectService(registry=temp_db)

        with pytest.raises(FileNotFoundError, match="Data directory not found"):
            service.find_recent_pdfs(data_dir="/nonexistent/directory")

    def test_find_recent_pdfs_no_pdfs(self, temp_db):
        """Test finding PDFs when no PDFs exist."""
        service = ProjectService(registry=temp_db)

        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir()

            with pytest.raises(FileNotFoundError, match="No PDF files found"):
                service.find_recent_pdfs(data_dir=empty_dir)

    def test_create_document_subset(self, temp_db):
        """Test creating document subsets with criteria."""
        service = ProjectService(registry=temp_db)

        # Add test documents with different statuses and dates
        from datetime import datetime, timedelta

        base_date = datetime.now()
        doc1 = Document(
            source_path=Path("/test1.pdf"),
            status=DocumentStatus.INDEXED,
            added_date=base_date - timedelta(days=1),
        )
        doc1.project_id = "test_project"

        doc2 = Document(
            source_path=Path("/test2.pdf"),
            status=DocumentStatus.PENDING,
            added_date=base_date,
        )
        doc2.project_id = "test_project"

        doc3 = Document(
            source_path=Path("/large_file.pdf"),
            status=DocumentStatus.INDEXED,
            added_date=base_date - timedelta(hours=12),
        )
        doc3.project_id = "test_project"

        temp_db.add_document(doc1)
        temp_db.add_document(doc2)
        temp_db.add_document(doc3)

        # Test filtering by status
        subset = service.create_document_subset(
            subset_name="indexed_docs",
            criteria={"status": "indexed"},
            project_id="test_project",
        )

        assert len(subset) == 2
        assert all(doc.status == DocumentStatus.INDEXED for doc in subset)

        # Test filtering by filename pattern
        subset = service.create_document_subset(
            subset_name="large_files",
            criteria={"filename_pattern": "large"},
            project_id="test_project",
        )

        assert len(subset) == 1
        assert "large" in subset[0].source_path.name

        # Test limiting results
        subset = service.create_document_subset(
            subset_name="limited",
            criteria={"limit": 1},
            project_id="test_project",
        )

        assert len(subset) == 1

    def test_get_project_stats(self, temp_db):
        """Test getting project statistics."""
        service = ProjectService(registry=temp_db)

        # Add test documents
        doc1 = Document(source_path=Path("/test1.pdf"), status=DocumentStatus.INDEXED)
        doc1.project_id = "test_project"
        doc2 = Document(source_path=Path("/test2.pdf"), status=DocumentStatus.PENDING)
        doc2.project_id = "test_project"
        doc3 = Document(source_path=Path("/test3.pdf"), status=DocumentStatus.FAILED)
        doc3.project_id = "test_project"

        temp_db.add_document(doc1)
        temp_db.add_document(doc2)
        temp_db.add_document(doc3)

        stats = service.get_project_stats("test_project")

        assert stats.project_id == "test_project"
        assert stats.total_documents == 3
        assert stats.indexed_count == 1
        assert stats.pending_count == 1
        assert stats.failed_count == 1

    def test_export_project_data(self, temp_db):
        """Test exporting project data."""
        service = ProjectService(registry=temp_db)

        # Add test documents
        doc1 = Document(
            source_path=Path("/test1.pdf"),
            status=DocumentStatus.INDEXED,
            title="Test Document 1",
            authors=["Author 1"],
        )
        doc1.project_id = "test_project"
        temp_db.add_document(doc1)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            result = service.export_project_data(
                project_id="test_project",
                output_file=output_file,
                include_content=False,
            )

            assert output_file.exists()
            assert result["documents_exported"] == 1
            assert result["file_size_kb"] > 0

            # Verify content
            import json
            with output_file.open() as f:
                data = json.load(f)

            assert data["project_id"] == "test_project"
            assert len(data["documents"]) == 1
            assert data["documents"][0]["title"] == "Test Document 1"

        finally:
            if output_file.exists():
                output_file.unlink()

    def test_list_projects(self, temp_db):
        """Test listing all projects."""
        service = ProjectService(registry=temp_db)

        # Add documents from different projects
        doc1 = Document(source_path=Path("/test1.pdf"), status=DocumentStatus.INDEXED)
        doc1.project_id = "project_a"
        doc2 = Document(source_path=Path("/test2.pdf"), status=DocumentStatus.PENDING)
        doc2.project_id = "project_b"
        doc3 = Document(source_path=Path("/test3.pdf"), status=DocumentStatus.INDEXED)
        doc3.project_id = "project_a"

        temp_db.add_document(doc1)
        temp_db.add_document(doc2)
        temp_db.add_document(doc3)

        projects = service.list_projects()

        assert len(projects) >= 2  # At least project_a and project_b
        assert "project_a" in projects
        assert "project_b" in projects

        # Check project_a stats
        project_a_stats = projects["project_a"]
        assert project_a_stats.total_documents == 2
        assert project_a_stats.indexed_count == 2
