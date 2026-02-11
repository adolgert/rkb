"""Tests for canonical store behaviors."""

import hashlib
from pathlib import Path

import pytest

import rkb.collection.canonical_store as canonical_store_module
from rkb.collection.canonical_store import canonical_dir, is_stored, store_pdf
from rkb.collection.hashing import hash_file_sha256


def test_canonical_dir_layout():
    library_root = Path("/tmp/library")
    content_hash = "ab" * 32

    path = canonical_dir(library_root, content_hash)

    assert path == Path("/tmp/library/sha256/ab/ab") / content_hash


def test_store_pdf_round_trip_and_idempotency(tmp_path):
    library_root = tmp_path / "library"
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"pdf payload")

    content_hash = hash_file_sha256(source_path)
    stored = store_pdf(library_root, source_path, content_hash, "Smith 2024 Study.pdf")

    assert stored.exists()
    assert stored.parent == canonical_dir(library_root, content_hash)
    assert hash_file_sha256(stored) == content_hash
    assert is_stored(library_root, content_hash)

    stored_again = store_pdf(library_root, source_path, content_hash, "Ignored Name.pdf")
    assert stored_again == stored


def test_store_pdf_rejects_wrong_hash(tmp_path):
    library_root = tmp_path / "library"
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"actual bytes")
    wrong_hash = hashlib.sha256(b"different bytes").hexdigest()

    with pytest.raises(ValueError, match="does not match"):
        store_pdf(library_root, source_path, wrong_hash, "Name.pdf")


def test_store_pdf_can_skip_source_verification_for_trusted_hash(monkeypatch, tmp_path):
    library_root = tmp_path / "library"
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"pdf payload")
    content_hash = hash_file_sha256(source_path)

    calls: list[Path] = []
    original_hash = canonical_store_module.hash_file_sha256

    def tracking_hash(path: Path) -> str:
        calls.append(path)
        return original_hash(path)

    monkeypatch.setattr(canonical_store_module, "hash_file_sha256", tracking_hash)

    stored = store_pdf(
        library_root,
        source_path,
        content_hash,
        "Trusted.pdf",
        verify_source=False,
    )

    assert stored.exists()
    assert source_path not in calls
