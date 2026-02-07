"""Tests for Zotero synchronization helpers."""

from pathlib import Path

import pytest

from rkb.collection.catalog import Catalog
from rkb.collection.hashing import hash_file_sha256
from rkb.collection.zotero_sync import (
    import_to_zotero,
    is_in_zotero,
    scan_zotero_hashes,
    sync_batch_to_zotero,
)


class FakeZotero:
    """Minimal pyzotero-like client mock."""

    def __init__(self):
        self.created: list[dict] = []
        self.attachments: list[tuple[list[str], str]] = []
        self.item_counter = 0
        self.attachment_counter = 0
        self.failures_by_title: dict[str, list[Exception]] = {}

    def item_template(self, _item_type):
        return {"title": ""}

    def create_items(self, items):
        title = items[0]["title"]
        failures = self.failures_by_title.get(title)
        if failures:
            raise failures.pop(0)

        self.item_counter += 1
        item_key = f"ITEM{self.item_counter}"
        self.created.append({"title": title, "item_key": item_key})
        return {"successful": {"0": {"key": item_key}}}

    def attachment_simple(self, file_paths, item_key):
        self.attachment_counter += 1
        attachment_key = f"ATT{self.attachment_counter}"
        self.attachments.append((file_paths, item_key))
        return {"successful": {"0": {"key": attachment_key}}}


def test_scan_zotero_hashes(tmp_path):
    storage = tmp_path / "storage"
    (storage / "ABC12345").mkdir(parents=True)
    (storage / "XYZ98765").mkdir(parents=True)
    first = storage / "ABC12345" / "a.pdf"
    second = storage / "XYZ98765" / "b.PDF"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    (storage / "ABC12345" / "notes.txt").write_text("ignore", encoding="utf-8")

    hash_map = scan_zotero_hashes(storage)

    assert len(hash_map) == 2
    assert hash_map[hash_file_sha256(first)] == first.resolve()
    assert hash_map[hash_file_sha256(second)] == second.resolve()


def test_import_to_zotero_calls_client(tmp_path):
    zot = FakeZotero()
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf bytes")

    item_key, attachment_key = import_to_zotero(pdf_path, "Display Name.pdf", zot)

    assert item_key == "ITEM1"
    assert attachment_key == "ATT1"
    assert zot.created[0]["title"] == "Display Name.pdf"
    assert zot.attachments[0] == ([str(pdf_path)], "ITEM1")


def test_is_in_zotero():
    hash_map = {"a" * 64: Path("/tmp/file.pdf")}
    assert is_in_zotero("a" * 64, hash_map)
    assert not is_in_zotero("b" * 64, hash_map)


def test_sync_batch_to_zotero_imports_only_missing(tmp_path):
    library_root = tmp_path / "library"
    db_path = library_root / "db" / "pdf_catalog.db"
    catalog = Catalog(db_path=db_path)
    catalog.initialize()

    existing_pdf = library_root / "sha256/existing.pdf"
    missing_pdf = library_root / "sha256/missing.pdf"
    existing_pdf.parent.mkdir(parents=True, exist_ok=True)
    existing_pdf.write_bytes(b"existing")
    missing_pdf.write_bytes(b"missing")
    existing_hash = hash_file_sha256(existing_pdf)
    missing_hash = hash_file_sha256(missing_pdf)

    catalog.add_canonical_file(
        existing_hash,
        str(existing_pdf),
        "existing.pdf",
        "existing.pdf",
        1,
        existing_pdf.stat().st_size,
    )
    catalog.add_canonical_file(
        missing_hash,
        str(missing_pdf),
        "missing.pdf",
        "missing.pdf",
        1,
        missing_pdf.stat().st_size,
    )

    zotero_hashes = {existing_hash: Path("/zotero/existing.pdf")}
    zot = FakeZotero()

    summary = sync_batch_to_zotero(
        hashes_to_import=[existing_hash, missing_hash],
        catalog=catalog,
        library_root=library_root,
        zot=zot,
        zotero_hashes=zotero_hashes,
    )

    assert summary == {"imported": 1, "skipped": 1, "failed": 0}
    assert len(zot.created) == 1
    assert zot.created[0]["title"] == "missing.pdf"

    unlinked = catalog.get_unlinked_to_zotero()
    assert existing_hash not in unlinked
    assert missing_hash not in unlinked
    catalog.close()


def test_sync_batch_to_zotero_retries_on_429(tmp_path):
    class RateLimitError(Exception):
        status = 429

    library_root = tmp_path / "library"
    db_path = library_root / "db" / "pdf_catalog.db"
    catalog = Catalog(db_path=db_path)
    catalog.initialize()

    pdf_path = library_root / "sha256/retry.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"retry")
    content_hash = hash_file_sha256(pdf_path)
    catalog.add_canonical_file(
        content_hash,
        str(pdf_path),
        "retry.pdf",
        "retry.pdf",
        1,
        pdf_path.stat().st_size,
    )

    zot = FakeZotero()
    zot.failures_by_title["retry.pdf"] = [RateLimitError("429"), RateLimitError("429")]
    sleeps: list[float] = []

    summary = sync_batch_to_zotero(
        hashes_to_import=[content_hash],
        catalog=catalog,
        library_root=library_root,
        zot=zot,
        zotero_hashes={},
        max_retries=3,
        base_backoff_seconds=0.5,
        sleep_func=sleeps.append,
    )

    assert summary == {"imported": 1, "skipped": 0, "failed": 0}
    assert sleeps == [0.5, 1.0]
    catalog.close()


def test_sync_batch_to_zotero_marks_failed_after_retry_exhaustion(tmp_path):
    class RateLimitError(Exception):
        status = 429

    library_root = tmp_path / "library"
    db_path = library_root / "db" / "pdf_catalog.db"
    catalog = Catalog(db_path=db_path)
    catalog.initialize()

    pdf_path = library_root / "sha256/fail.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"fail")
    content_hash = hash_file_sha256(pdf_path)
    catalog.add_canonical_file(
        content_hash,
        str(pdf_path),
        "fail.pdf",
        "fail.pdf",
        1,
        pdf_path.stat().st_size,
    )

    zot = FakeZotero()
    zot.failures_by_title["fail.pdf"] = [RateLimitError("429"), RateLimitError("429")]

    summary = sync_batch_to_zotero(
        hashes_to_import=[content_hash],
        catalog=catalog,
        library_root=library_root,
        zot=zot,
        zotero_hashes={},
        max_retries=1,
        base_backoff_seconds=0.1,
        sleep_func=lambda _seconds: None,
    )

    assert summary == {"imported": 0, "skipped": 0, "failed": 1}
    row = catalog.get_unlinked_to_zotero()
    assert content_hash in row
    catalog.close()


def test_scan_zotero_hashes_raises_for_missing_storage(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_zotero_hashes(tmp_path / "missing")
