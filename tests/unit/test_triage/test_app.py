"""Flask route tests for the triage web application."""

from rkb.collection.hashing import hash_file_sha256
from rkb.triage.app import create_app


def test_triage_app_approve_reject_flow(monkeypatch, tmp_path):
    downloads_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    downloads_dir.mkdir()
    staging_dir.mkdir()
    db_path = staging_dir / "triage.db"

    pdf_path = downloads_dir / "sample.pdf"
    pdf_path.write_bytes(b"sample bytes")
    content_hash = hash_file_sha256(pdf_path)

    monkeypatch.setattr(
        "rkb.triage.app.render_pdf_pages_base64",
        lambda _path, max_pages=2: ["img1", "img2"][:max_pages],
    )

    app = create_app(downloads_dir=downloads_dir, staging_dir=staging_dir, db_path=db_path)
    client = app.test_client()

    review = client.get("/")
    assert review.status_code == 200
    assert b"sample.pdf" in review.data

    approve = client.post(
        f"/pdf/{content_hash}/decide",
        data={"decision": "approved", "path": str(pdf_path)},
    )
    assert approve.status_code == 200
    assert approve.get_json()["decision"] == "approved"

    queue = client.get("/queue")
    assert queue.status_code == 200
    assert b"sample.pdf" in queue.data

    staged_files = list(staging_dir.glob("*.pdf"))
    assert len(staged_files) == 1

    pages = client.get(f"/pdf/{content_hash}/pages", query_string={"path": str(pdf_path)})
    assert pages.status_code == 200
    assert pages.get_json()["pages"] == ["img1", "img2"]

    stats_after_approve = client.get("/api/stats").get_json()
    assert stats_after_approve["approved"] == 1
    assert stats_after_approve["rejected"] == 0

    reject = client.post(
        f"/pdf/{content_hash}/decide",
        data={"decision": "rejected", "path": str(pdf_path)},
    )
    assert reject.status_code == 200
    assert reject.get_json()["decision"] == "rejected"
    assert list(staging_dir.glob("*.pdf")) == []

    history = client.get("/history")
    assert history.status_code == 200
    assert b"approved" in history.data
    assert b"rejected" in history.data

    stats_after_reject = client.get("/api/stats").get_json()
    assert stats_after_reject["approved"] == 0
    assert stats_after_reject["rejected"] == 1


def test_triage_app_remembers_decision_when_file_reappears(tmp_path):
    downloads_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    downloads_dir.mkdir()
    staging_dir.mkdir()
    db_path = staging_dir / "triage.db"

    pdf_path = downloads_dir / "paper.pdf"
    pdf_payload = b"identical bytes"
    pdf_path.write_bytes(pdf_payload)
    content_hash = hash_file_sha256(pdf_path)

    app = create_app(downloads_dir=downloads_dir, staging_dir=staging_dir, db_path=db_path)
    client = app.test_client()

    response = client.post(
        f"/pdf/{content_hash}/decide",
        data={"decision": "approved", "path": str(pdf_path)},
    )
    assert response.status_code == 200

    pdf_path.unlink()
    pdf_path.write_bytes(pdf_payload)

    review = client.get("/")
    assert review.status_code == 200
    assert b"Decision: approved" in review.data


def test_triage_app_recursive_scan_can_be_enabled(tmp_path):
    downloads_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staging"
    nested_dir = downloads_dir / "nested"
    downloads_dir.mkdir()
    staging_dir.mkdir()
    nested_dir.mkdir()

    nested_pdf = nested_dir / "nested.pdf"
    nested_pdf.write_bytes(b"nested bytes")

    default_app = create_app(
        downloads_dir=downloads_dir,
        staging_dir=staging_dir,
        db_path=staging_dir / "default.db",
    )
    default_client = default_app.test_client()
    default_review = default_client.get("/")
    assert default_review.status_code == 200
    assert b"nested.pdf" not in default_review.data

    recursive_app = create_app(
        downloads_dir=downloads_dir,
        staging_dir=staging_dir,
        db_path=staging_dir / "recursive.db",
        recursive_scan=True,
    )
    recursive_client = recursive_app.test_client()
    recursive_review = recursive_client.get("/")
    assert recursive_review.status_code == 200
    assert b"nested.pdf" in recursive_review.data
