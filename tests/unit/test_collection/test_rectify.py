"""Tests for rectify collection reconciliation."""

import rkb.collection.rectify as rectify_module
from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig
from rkb.collection.hashing import hash_file_sha256
from rkb.collection.rectify import rectify_collection


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


def test_rectify_report_has_no_side_effects(tmp_path):
    config = _config_for_tmp(tmp_path)
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "one.pdf").write_bytes(b"same")
    (scan_dir / "two.pdf").write_bytes(b"same")
    (scan_dir / "three.pdf").write_bytes(b"different")

    summary = rectify_collection(
        scan_directories=[scan_dir],
        config=config,
        report=True,
        skip_zotero=True,
    )

    assert summary.total_files_found == 3
    assert summary.unique_pdfs == 2
    assert summary.duplicate_files == 1
    assert summary.canonical_new == 2
    assert summary.copied_to_canonical == 0
    assert summary.failed == 0
    assert not config.catalog_db.exists()
    assert not (config.library_root / "sha256").exists()


def test_rectify_fills_forward_and_reverse_gaps_and_is_idempotent(tmp_path):
    config = _config_for_tmp(tmp_path)

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "a1.pdf").write_bytes(b"alpha")
    (scan_dir / "a2.pdf").write_bytes(b"alpha")
    (scan_dir / "b.pdf").write_bytes(b"beta")

    zotero_dir = config.zotero_storage / "ABC12345"
    zotero_dir.mkdir(parents=True)
    zotero_pdf = zotero_dir / "zonly.pdf"
    zotero_pdf.write_bytes(b"gamma")
    zotero_hash = hash_file_sha256(zotero_pdf)

    first = rectify_collection(
        scan_directories=[scan_dir],
        config=config,
        skip_zotero=True,
    )
    second = rectify_collection(
        scan_directories=[scan_dir],
        config=config,
        skip_zotero=True,
    )

    assert first.total_files_found == 3
    assert first.unique_pdfs == 2
    assert first.duplicate_files == 1
    assert first.canonical_new == 2
    assert first.zotero_reverse_missing_store == 1
    assert first.copied_to_canonical == 3
    assert first.failed == 0

    catalog = Catalog(config.catalog_db)
    stats = catalog.get_statistics()
    hashes = set(catalog.list_canonical_hashes())
    catalog.close()

    assert stats["canonical_files"] == 3
    assert stats["source_sightings"] == 4
    assert zotero_hash in hashes

    assert second.canonical_new == 0
    assert second.canonical_already == 2
    assert second.zotero_reverse_missing_store == 0
    assert second.copied_to_canonical == 0
    assert second.failed == 0


def test_rectify_with_zotero_sync_updates_summary(monkeypatch, tmp_path):
    config = _config_for_tmp(tmp_path)
    config.zotero_storage.mkdir(parents=True)

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "paper.pdf").write_bytes(b"paper")

    calls: dict[str, list] = {"hashes": []}

    monkeypatch.setattr(rectify_module, "scan_zotero_hashes", lambda _path: {})
    monkeypatch.setattr(rectify_module, "_build_zotero_client", lambda _cfg: object())

    def fake_sync_batch_to_zotero(**kwargs):
        calls["hashes"].append(kwargs["hashes_to_import"])
        return {"imported": 1, "skipped": 0, "failed": 0}

    monkeypatch.setattr(rectify_module, "sync_batch_to_zotero", fake_sync_batch_to_zotero)

    summary = rectify_collection(
        scan_directories=[scan_dir],
        config=config,
        skip_zotero=False,
    )

    assert summary.copied_to_canonical == 1
    assert summary.zotero_to_import == 1
    assert summary.zotero_existing == 0
    assert summary.imported_to_zotero == 1
    assert summary.failed == 0
    assert len(calls["hashes"]) == 1
    assert len(calls["hashes"][0]) == 1


def test_rectify_zotero_setup_failure_marks_files_failed(tmp_path):
    config = _config_for_tmp(tmp_path)
    config.zotero_storage.mkdir(parents=True)

    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "one.pdf").write_bytes(b"one")
    (scan_dir / "two.pdf").write_bytes(b"two")

    summary = rectify_collection(
        scan_directories=[scan_dir],
        config=config,
        skip_zotero=False,
    )

    assert summary.copied_to_canonical == 2
    assert summary.failed == 2
    assert len(summary.failures) == 2
    assert all("zotero setup error" in failure.error for failure in summary.failures)
