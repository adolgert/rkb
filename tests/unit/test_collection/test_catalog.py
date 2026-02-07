"""Tests for SQLite catalog operations."""

import sqlite3

import pytest

from rkb.collection.canonical_store import store_pdf
from rkb.collection.catalog import Catalog
from rkb.collection.hashing import hash_file_sha256


def test_catalog_crud_in_memory():
    catalog = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    catalog.initialize()

    content_hash = "a" * 64
    catalog.add_canonical_file(
        content_sha256=content_hash,
        canonical_path="/tmp/sha256/aa/aa/hash/file.pdf",
        display_name="File.pdf",
        original_filename="original.pdf",
        page_count=2,
        file_size_bytes=1234,
    )

    assert catalog.is_known(content_hash)
    row = catalog.get_canonical_file(content_hash)
    assert row is not None
    assert row["display_name"] == "File.pdf"


def test_catalog_duplicate_hash_raises():
    catalog = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    catalog.initialize()
    content_hash = "b" * 64

    catalog.add_canonical_file(
        content_sha256=content_hash,
        canonical_path="/tmp/one.pdf",
        display_name="One.pdf",
        original_filename="one.pdf",
        page_count=1,
        file_size_bytes=11,
    )

    with pytest.raises(sqlite3.IntegrityError):
        catalog.add_canonical_file(
            content_sha256=content_hash,
            canonical_path="/tmp/two.pdf",
            display_name="Two.pdf",
            original_filename="two.pdf",
            page_count=1,
            file_size_bytes=22,
        )


def test_catalog_unlinked_and_statistics():
    catalog = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    catalog.initialize()
    h1 = "1" * 64
    h2 = "2" * 64

    catalog.add_canonical_file(h1, "/tmp/one.pdf", "One.pdf", "one.pdf", 1, 10)
    catalog.add_canonical_file(h2, "/tmp/two.pdf", "Two.pdf", "two.pdf", 1, 20)
    catalog.add_source_sighting(h1, "/inbox/one.pdf", "machine-1")
    catalog.set_zotero_link(h1, "ITEM1", "imported")
    catalog.set_zotero_link(h2, None, "failed", error_message="bad upload")
    catalog.log_action(h1, "ingested", "/inbox/one.pdf", "ok")

    assert catalog.get_unlinked_to_zotero() == [h2]

    stats = catalog.get_statistics()
    assert stats["canonical_files"] == 2
    assert stats["source_sightings"] == 1
    assert stats["zotero_links"] == 2
    assert stats["ingest_log"] == 1
    assert stats["unlinked_to_zotero"] == 1


def test_catalog_status_helpers_and_recent_log():
    catalog = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    catalog.initialize()
    h1 = "3" * 64
    h2 = "4" * 64
    h3 = "5" * 64

    catalog.add_canonical_file(h1, "/tmp/one.pdf", "One.pdf", "one.pdf", 1, 100)
    catalog.add_canonical_file(h2, "/tmp/two.pdf", "Two.pdf", "two.pdf", 1, 200)
    catalog.add_canonical_file(h3, "/tmp/three.pdf", "Three.pdf", "three.pdf", 1, 300)

    catalog.set_zotero_link(h1, "ITEM1", "imported")
    catalog.set_zotero_link(h2, None, "pending")
    catalog.log_action(h1, "ingested", "/inbox/one.pdf", "ok")
    catalog.log_action(h2, "failed", "/inbox/two.pdf", "no space")

    assert catalog.get_zotero_linked_count() == 1
    assert catalog.get_canonical_store_bytes() == 600
    assert catalog.get_unlinked_to_zotero() == [h2, h3]

    recent = catalog.get_recent_ingest_log(limit=1)
    assert len(recent) == 1
    assert recent[0]["content_sha256"] == h2
    assert recent[0]["action"] == "failed"


def test_round_trip_hash_store_catalog_query(tmp_path):
    library_root = tmp_path / "library"
    db_path = library_root / "db" / "pdf_catalog.db"
    source_path = tmp_path / "paper.pdf"
    source_path.write_bytes(b"paper bytes for roundtrip")

    content_hash = hash_file_sha256(source_path)
    stored_path = store_pdf(library_root, source_path, content_hash, "Round Trip.pdf")

    catalog = Catalog(db_path=db_path)
    catalog.initialize()
    catalog.add_canonical_file(
        content_sha256=content_hash,
        canonical_path=str(stored_path),
        display_name=stored_path.name,
        original_filename=source_path.name,
        page_count=None,
        file_size_bytes=source_path.stat().st_size,
    )
    catalog.add_source_sighting(content_hash, str(source_path), "test-machine")

    row = catalog.get_canonical_file(content_hash)
    assert row is not None
    assert row["canonical_path"] == str(stored_path)
    assert catalog.is_known(content_hash)
