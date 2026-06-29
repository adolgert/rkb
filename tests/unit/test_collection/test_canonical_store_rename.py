"""Tests for rename_pdf() in canonical_store."""

from pathlib import Path

import pytest

from rkb.collection.canonical_store import rename_pdf


def _setup_hash_dir(tmp_path: Path, content_sha256: str, filename: str) -> Path:
    """Create a canonical hash directory with a PDF file."""
    prefix1, prefix2 = content_sha256[:2], content_sha256[2:4]
    hash_dir = tmp_path / "sha256" / prefix1 / prefix2 / content_sha256
    hash_dir.mkdir(parents=True)
    pdf = hash_dir / filename
    pdf.write_bytes(b"%PDF-1.4 test content")
    return pdf


_HASH = "a" * 64


class TestRenamePdf:
    def test_happy_path(self, tmp_path):
        _setup_hash_dir(tmp_path, _HASH, "old_name.pdf")
        new_path = rename_pdf(tmp_path, _HASH, "New Paper Title")
        assert new_path.name == "New Paper Title.pdf"
        assert new_path.exists()

    def test_appends_pdf_suffix(self, tmp_path):
        _setup_hash_dir(tmp_path, _HASH, "old.pdf")
        new_path = rename_pdf(tmp_path, _HASH, "no_suffix")
        assert new_path.name == "no_suffix.pdf"

    def test_preserves_pdf_suffix(self, tmp_path):
        _setup_hash_dir(tmp_path, _HASH, "old.pdf")
        new_path = rename_pdf(tmp_path, _HASH, "already.pdf")
        assert new_path.name == "already.pdf"

    def test_same_name_noop(self, tmp_path):
        pdf = _setup_hash_dir(tmp_path, _HASH, "same.pdf")
        new_path = rename_pdf(tmp_path, _HASH, "same.pdf")
        assert new_path == pdf
        assert new_path.exists()

    def test_missing_pdf_raises(self, tmp_path):
        prefix1, prefix2 = _HASH[:2], _HASH[2:4]
        hash_dir = tmp_path / "sha256" / prefix1 / prefix2 / _HASH
        hash_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            rename_pdf(tmp_path, _HASH, "anything")
