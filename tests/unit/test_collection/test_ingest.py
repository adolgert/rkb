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
