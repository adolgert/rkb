"""Tests for the zotero_push core logic (pyzotero client fully mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rkb.collection.catalog import Catalog
from rkb.collection.zotero_push import (
    ZoteroPushSummary,
    build_zotero_item,
    push_batch_to_zotero,
)


def _make_catalog(tmp_path):
    catalog = Catalog(tmp_path / "db" / "pdf_catalog.db")
    catalog.initialize()
    return catalog


def _seed(
    catalog,
    tmp_path,
    sha,
    *,
    title="A Study of Things",
    doc_type="journal-article",
    authors=("Ada Lovelace", "Alan Turing"),
    journal="Journal of Testing",
    year=2021,
    abstract="An abstract.",
    make_pdf=True,
):
    pdf_path = tmp_path / f"{sha}.pdf"
    if make_pdf:
        pdf_path.write_bytes(b"%PDF-1.4 fake")
    catalog.add_canonical_file(
        content_sha256=sha,
        canonical_path=str(pdf_path),
        display_name=f"{sha[:6]}.pdf",
        original_filename="orig.pdf",
        page_count=3,
        file_size_bytes=100,
    )
    if title is not None:
        catalog.set_resolved_metadata(
            sha,
            title=title,
            authors=list(authors) if authors else None,
            year=year,
            journal=journal,
            abstract=abstract,
            doc_type=doc_type,
        )
    return pdf_path


def _happy_client(item_key="ITEMKEY1", att_key="ATTKEY1"):
    zot = MagicMock()
    zot.create_items.return_value = {"successful": {"0": {"key": item_key}}}
    zot.attachment_simple.return_value = {"successful": {"0": {"key": att_key}}}
    return zot


# --- item construction -------------------------------------------------------


def test_build_item_field_mapping_and_extra():
    metadata = {
        "title": "Deep Nets",
        "abstract": "We train nets.",
        "year": 2020,
        "journal": "Nature",
        "doc_type": "journal-article",
        "authors": ["Jane Doe", "John Roe"],
    }
    item = build_zotero_item(metadata, "a" * 64)

    assert item["itemType"] == "journalArticle"
    assert item["title"] == "Deep Nets"
    assert item["abstractNote"] == "We train nets."
    assert item["date"] == "2020"
    assert item["publicationTitle"] == "Nature"
    assert item["extra"] == f"rkb:sha256 {'a' * 64}"
    assert item["creators"] == [
        {"creatorType": "author", "name": "Jane Doe"},
        {"creatorType": "author", "name": "John Roe"},
    ]


def test_build_item_venue_field_per_type():
    base = {"title": "T", "journal": "Venue", "authors": []}
    assert build_zotero_item({**base, "doc_type": "preprint"}, "h")["repository"] == "Venue"
    assert (
        build_zotero_item({**base, "doc_type": "proceedings-article"}, "h")["conferenceName"]
        == "Venue"
    )
    assert build_zotero_item({**base, "doc_type": "book-chapter"}, "h")["bookTitle"] == "Venue"
    # report has no natural venue field: journal omitted, type defaults preserved.
    report = build_zotero_item({**base, "doc_type": "report"}, "h")
    assert report["itemType"] == "report"
    assert "publicationTitle" not in report
    # unknown doc_type falls back to journalArticle.
    assert build_zotero_item({"title": "T", "doc_type": "weird"}, "h")["itemType"] == (
        "journalArticle"
    )


def test_build_item_handles_missing_optional_fields():
    item = build_zotero_item({"title": "Only Title"}, "h")
    assert item["abstractNote"] == ""
    assert "date" not in item
    assert item["creators"] == []


# --- push happy path ---------------------------------------------------------


def test_happy_path_records_keys(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "a" * 64
    _seed(catalog, tmp_path, sha)
    zot = _happy_client()

    summary = push_batch_to_zotero(catalog, zot, sleep_func=lambda _s: None)

    assert summary.pushed == 1
    assert summary.failed == 0
    assert summary.skipped_no_metadata == 0
    link = catalog.get_zotero_link(sha)
    assert link["status"] == "imported"
    assert link["zotero_item_key"] == "ITEMKEY1"
    assert link["zotero_attachment_key"] == "ATTKEY1"
    # attachment created against the parent item key.
    zot.attachment_simple.assert_called_once()
    assert zot.attachment_simple.call_args[0][1] == "ITEMKEY1"


def test_alternate_success_response_shape(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "b" * 64
    _seed(catalog, tmp_path, sha)
    zot = MagicMock()
    zot.create_items.return_value = {"success": {"0": "IK"}}
    zot.attachment_simple.return_value = {"success": {"0": "AK"}}

    summary = push_batch_to_zotero(catalog, zot, sleep_func=lambda _s: None)

    assert summary.pushed == 1
    link = catalog.get_zotero_link(sha)
    assert link["zotero_item_key"] == "IK"
    assert link["zotero_attachment_key"] == "AK"


def test_untitled_docs_skipped(tmp_path):
    catalog = _make_catalog(tmp_path)
    _seed(catalog, tmp_path, "a" * 64, title=None)  # no resolved metadata
    _seed(catalog, tmp_path, "b" * 64)  # titled
    zot = _happy_client()

    summary = push_batch_to_zotero(catalog, zot, sleep_func=lambda _s: None)

    assert summary.pushed == 1
    assert summary.skipped_no_metadata == 1
    assert zot.create_items.call_count == 1
    # untitled doc never linked
    assert catalog.get_zotero_link("a" * 64) is None


def test_missing_file_marks_failed_not_crash(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "c" * 64
    _seed(catalog, tmp_path, sha, make_pdf=False)
    zot = _happy_client()

    summary = push_batch_to_zotero(catalog, zot, sleep_func=lambda _s: None)

    assert summary.pushed == 0
    assert summary.failed == 1
    assert catalog.get_zotero_link(sha)["status"] == "failed"
    zot.create_items.assert_not_called()


# --- rate limiting -----------------------------------------------------------


class _RateLimitError(Exception):
    def __init__(self, message="HTTP 429 Too Many Requests"):
        super().__init__(message)
        self.status = 429


def test_429_retry_then_success(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "a" * 64
    _seed(catalog, tmp_path, sha)
    zot = MagicMock()
    zot.create_items.side_effect = [
        _RateLimitError(),
        {"successful": {"0": {"key": "IK"}}},
    ]
    zot.attachment_simple.return_value = {"successful": {"0": {"key": "AK"}}}
    slept = []

    summary = push_batch_to_zotero(catalog, zot, sleep_func=slept.append)

    assert summary.pushed == 1
    assert zot.create_items.call_count == 2
    assert slept  # backoff was applied
    assert catalog.get_zotero_link(sha)["status"] == "imported"


def test_persistent_429_aborts_and_leaves_remaining(tmp_path):
    catalog = _make_catalog(tmp_path)
    # 'b' newest, 'a' older -> ensure both present; both would be pushed.
    _seed(catalog, tmp_path, "a" * 64)
    _seed(catalog, tmp_path, "b" * 64)
    zot = MagicMock()
    zot.create_items.side_effect = _RateLimitError()

    summary = push_batch_to_zotero(
        catalog, zot, max_retries=2, sleep_func=lambda _s: None
    )

    assert summary.aborted_rate_limited is True
    assert summary.exit_code() == 2
    # Only one document was attempted (twice, same hash) before aborting.
    assert summary.pushed == 0
    # The other document was never pushed and remains a candidate for next run.
    remaining = catalog.get_zotero_push_candidates()
    unlinked_shas = {row["content_sha256"] for row in remaining}
    # at least the untouched one remains unlinked
    assert len(unlinked_shas) >= 1


def test_failed_rows_retried_on_next_run(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "a" * 64
    _seed(catalog, tmp_path, sha)

    # First run: non-rate-limit failure marks the row failed.
    failing = MagicMock()
    failing.create_items.side_effect = RuntimeError("boom")
    summary1 = push_batch_to_zotero(catalog, failing, sleep_func=lambda _s: None)
    assert summary1.failed == 1
    assert catalog.get_zotero_link(sha)["status"] == "failed"

    # Failed row is still a candidate.
    assert sha in {row["content_sha256"] for row in catalog.get_zotero_push_candidates()}

    # Second run: succeeds.
    ok = _happy_client()
    summary2 = push_batch_to_zotero(catalog, ok, sleep_func=lambda _s: None)
    assert summary2.pushed == 1
    assert catalog.get_zotero_link(sha)["status"] == "imported"


def test_limit_respected(tmp_path):
    catalog = _make_catalog(tmp_path)
    for ch in "abcde":
        _seed(catalog, tmp_path, ch * 64)
    zot = _happy_client()

    summary = push_batch_to_zotero(catalog, zot, limit=2, sleep_func=lambda _s: None)

    assert summary.pushed == 2
    assert zot.create_items.call_count == 2


def test_retry_after_header_honored(tmp_path):
    catalog = _make_catalog(tmp_path)
    sha = "a" * 64
    _seed(catalog, tmp_path, sha)

    class _Resp:
        def __init__(self):
            self.headers = {"Retry-After": "7"}
            self.status_code = 429

    err = Exception("429")
    err.response = _Resp()

    zot = MagicMock()
    zot.create_items.side_effect = [err, {"successful": {"0": {"key": "IK"}}}]
    zot.attachment_simple.return_value = {"successful": {"0": {"key": "AK"}}}
    slept = []

    summary = push_batch_to_zotero(catalog, zot, sleep_func=slept.append)

    assert summary.pushed == 1
    assert slept == [7.0]


def test_summary_exit_codes():
    assert ZoteroPushSummary().exit_code() == 0
    assert ZoteroPushSummary(pushed=3).exit_code() == 0
    assert ZoteroPushSummary(failed=1).exit_code() == 2
    assert ZoteroPushSummary(aborted_rate_limited=True).exit_code() == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
