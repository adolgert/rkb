"""Shared fixtures for system-level tests."""

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with standard directory structure.

    Uses pytest's tmp_path fixture (NOT tempfile module).
    tmp_path is automatically cleaned up after test completion.
    """
    workspace = tmp_path / "rkb_test"
    workspace.mkdir()

    # Standard directories
    (workspace / "data").mkdir()
    (workspace / "extractions").mkdir()  # For .mmd files

    return {
        "root": workspace,
        "data_dir": workspace / "data",
        "db_path": workspace / "test.db",
        "vector_db": workspace / "chroma_db",
        "extraction_dir": workspace / "extractions",
        "checkpoint_dir": workspace / ".checkpoints",
    }


@pytest.fixture
def sample_pdfs(temp_workspace):
    """Copy sample PDFs from test data to temp workspace."""
    data_initial = Path("data/initial")
    if not data_initial.exists():
        pytest.skip("No test data available in data/initial")

    # Copy first 2 smallest PDFs
    pdf_files = sorted(data_initial.glob("**/*.pdf"), key=lambda p: p.stat().st_size)[:2]

    if not pdf_files:
        pytest.skip("No PDF files found in data/initial")

    copied_files = []
    for pdf in pdf_files:
        dest = temp_workspace["data_dir"] / pdf.name
        shutil.copy(pdf, dest)
        copied_files.append(dest)

    return copied_files


@pytest.fixture
def cli_args_base(temp_workspace):
    """Base CLI arguments with temp paths for all storage locations."""
    return {
        "db_path": temp_workspace["db_path"],
        "vector_db_path": temp_workspace["vector_db"],
        "extraction_dir": temp_workspace["extraction_dir"],
        "checkpoint_dir": temp_workspace["checkpoint_dir"],
        "verbose": False,
    }
