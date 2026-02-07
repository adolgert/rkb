"""Tests for triage decision persistence."""

from rkb.triage.decisions import TriageDecisionStore


def test_set_and_update_decision_records_history(tmp_path):
    db_path = tmp_path / "triage.db"
    store = TriageDecisionStore(db_path)
    store.initialize()

    content_hash = "a" * 64
    store.set_decision(
        content_sha256=content_hash,
        decision="approved",
        original_path="/tmp/a.pdf",
        original_filename="a.pdf",
        file_size_bytes=10,
        page_count=1,
        staged_path="/tmp/staged/a.pdf",
    )
    first = store.get_decision(content_hash)
    assert first is not None
    assert first["decision"] == "approved"

    store.set_decision(
        content_sha256=content_hash,
        decision="rejected",
        original_path="/tmp/a.pdf",
        original_filename="a.pdf",
        file_size_bytes=10,
        page_count=1,
        staged_path=None,
    )
    second = store.get_decision(content_hash)
    assert second is not None
    assert second["decision"] == "rejected"
    assert second["staged_path"] is None

    # Setting the same decision again should not append another history row.
    store.set_decision(
        content_sha256=content_hash,
        decision="rejected",
        original_path="/tmp/a.pdf",
        original_filename="a.pdf",
        file_size_bytes=10,
        page_count=1,
        staged_path=None,
    )

    history = store.list_history()
    assert len(history) == 2
    assert history[0]["new_decision"] in {"approved", "rejected"}
    assert history[1]["new_decision"] in {"approved", "rejected"}

    stats = store.get_stats()
    assert stats["approved"] == 0
    assert stats["rejected"] == 1
    assert stats["total"] == 1
    assert stats["history"] == 2
    store.close()

