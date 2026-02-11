"""Tests for ingest orchestration."""

import rkb.collection.ingest as ingest_module
from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig
from rkb.collection.ingest import ingest_directories


def _config_for_tmp(tmp_path):
    library_root = tmp_path / "library"
    return CollectionConfig(
        library_root=library_root,
        catalog_db=library_root / "db" / "pdf_catalog.db",
        zotero_storage=tmp_path / "zotero",
        box_staging=tmp_path / "staging",
        work_downloads=tmp_path / "downloads",
        machine_id="test-machine",
        zotero_library_id=None,
        zotero_api_key=None,
        zotero_library_type="user",
    )


def test_ingest_round_trip_and_idempotent(tmp_path):
    config = _config_for_tmp(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pdf_path = inbox / "paper.pdf"
    pdf_path.write_bytes(b"paper bytes")

    first = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
    )
    second = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
    )

    assert first.scanned == 1
    assert first.new == 1
    assert first.duplicate == 0
    assert first.failed == 0

    assert second.scanned == 1
    assert second.new == 0
    assert second.duplicate == 1
    assert second.failed == 0

    catalog = Catalog(config.catalog_db)
    stats = catalog.get_statistics()
    catalog.close()
    assert stats["canonical_files"] == 1
    assert stats["source_sightings"] == 1


def test_ingest_dry_run_has_no_side_effects(tmp_path):
    config = _config_for_tmp(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "paper.pdf").write_bytes(b"dry run bytes")

    summary = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=True,
        skip_zotero=True,
        no_display_name=True,
    )

    assert summary.scanned == 1
    assert summary.new == 1
    assert summary.failed == 0
    assert not config.catalog_db.exists()
    assert not (config.library_root / "sha256").exists()


def test_ingest_continues_after_file_failure(monkeypatch, tmp_path):
    config = _config_for_tmp(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    good_pdf = inbox / "good.pdf"
    bad_pdf = inbox / "bad.pdf"
    good_pdf.write_bytes(b"good bytes")
    bad_pdf.write_bytes(b"bad bytes")

    original = ingest_module.hash_file_sha256

    def flaky_hash(path):
        if path.name == "bad.pdf":
            raise OSError("cannot read hash")
        return original(path)

    monkeypatch.setattr(ingest_module, "hash_file_sha256", flaky_hash)

    summary = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
    )

    assert summary.scanned == 2
    assert summary.new == 1
    assert summary.failed == 1
    assert len(summary.failures) == 1
    assert summary.failures[0].path.endswith("bad.pdf")
    assert "cannot read hash" in summary.failures[0].error


def test_ingest_with_zotero_sync_updates_summary(monkeypatch, tmp_path):
    config = _config_for_tmp(tmp_path)
    config.zotero_library_id = "12345"
    config.zotero_api_key = "token"

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pdf_path = inbox / "paper.pdf"
    pdf_path.write_bytes(b"paper bytes")

    calls: dict[str, list] = {"hashes": []}

    monkeypatch.setattr(ingest_module, "scan_zotero_hashes", lambda _path: {})
    monkeypatch.setattr(ingest_module, "build_zotero_client", lambda _cfg: object())

    def fake_sync_batch_to_zotero(**kwargs):
        calls["hashes"].append(kwargs["hashes_to_import"])
        return {"imported": 1, "skipped": 0, "failed": 0}

    monkeypatch.setattr(ingest_module, "sync_batch_to_zotero", fake_sync_batch_to_zotero)

    summary = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=False,
        no_display_name=True,
    )

    assert summary.new == 1
    assert summary.zotero_imported == 1
    assert summary.zotero_existing == 0
    assert summary.failed == 0
    assert len(calls["hashes"]) == 1
    assert len(calls["hashes"][0]) == 1


def test_ingest_zotero_setup_failure_marks_files_failed(tmp_path):
    config = _config_for_tmp(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pdf_path = inbox / "paper.pdf"
    pdf_path.write_bytes(b"paper bytes")

    summary = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=False,
        no_display_name=True,
    )

    assert summary.new == 1
    assert summary.failed == 1
    assert any("zotero setup error" in failure.error for failure in summary.failures)


def test_ingest_zero_byte_pdf_is_failure_and_continues(tmp_path):
    config = _config_for_tmp(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "empty.pdf").write_bytes(b"")
    (inbox / "valid.pdf").write_bytes(b"valid bytes")

    summary = ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
    )

    assert summary.scanned == 2
    assert summary.new == 1
    assert summary.failed == 1
    assert any("Zero-byte PDF" in failure.error for failure in summary.failures)
