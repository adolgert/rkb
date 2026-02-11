"""Tests for triage staging management."""

from rkb.collection.hashing import hash_file_sha256
from rkb.triage.decisions import TriageDecisionStore
from rkb.triage.staging import rebuild_staging, remove_staged_file, stage_approved_file


def test_stage_approved_file_handles_name_collision(tmp_path):
    staging_dir = tmp_path / "staging"
    source_a = tmp_path / "a.pdf"
    source_b = tmp_path / "b.pdf"
    source_a.write_bytes(b"alpha")
    source_b.write_bytes(b"beta")

    hash_a = hash_file_sha256(source_a)
    hash_b = hash_file_sha256(source_b)

    first = stage_approved_file(source_a, "paper.pdf", hash_a, staging_dir)
    second = stage_approved_file(source_b, "paper.pdf", hash_b, staging_dir)

    assert first.name == "paper.pdf"
    assert second.name.startswith("paper_")
    assert second.suffix == ".pdf"
    assert first.read_bytes() != second.read_bytes()


def test_remove_staged_file_noops_on_missing(tmp_path):
    missing = tmp_path / "does-not-exist.pdf"
    remove_staged_file(missing)
    assert not missing.exists()


def test_rebuild_staging_reconstructs_approved_set(tmp_path):
    staging_dir = tmp_path / "staging"
    db_path = staging_dir / "triage.db"
    store = TriageDecisionStore(db_path)
    store.initialize()

    source_ok = tmp_path / "ok.pdf"
    source_missing = tmp_path / "missing.pdf"
    source_ok.write_bytes(b"ok")

    hash_ok = hash_file_sha256(source_ok)
    hash_missing = "f" * 64

    store.set_decision(
        content_sha256=hash_ok,
        decision="approved",
        original_path=str(source_ok),
        original_filename=source_ok.name,
        file_size_bytes=source_ok.stat().st_size,
        page_count=1,
        staged_path=None,
    )
    store.set_decision(
        content_sha256=hash_missing,
        decision="approved",
        original_path=str(source_missing),
        original_filename=source_missing.name,
        file_size_bytes=None,
        page_count=None,
        staged_path=None,
    )

    summary = rebuild_staging(staging_dir, store)
    assert summary == {"re_staged": 1, "missing_source": 1}

    staged_files = list(staging_dir.glob("*.pdf"))
    assert len(staged_files) == 1
    assert staged_files[0].name == source_ok.name

    row_ok = store.get_decision(hash_ok)
    row_missing = store.get_decision(hash_missing)
    assert row_ok is not None and row_ok["staged_path"] is not None
    assert row_missing is not None and row_missing["staged_path"] is None
    store.close()
