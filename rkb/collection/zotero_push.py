"""Push resolved catalog records into Zotero as bibliographic items.

Unlike the legacy standalone-attachment flow in ``zotero_sync``, this module
builds a proper bibliographic *item* from the catalog's own resolved metadata
and attaches the canonical PDF as a child. The kbase catalog is the definitive
record; Zotero is a browsable synced mirror. Every pushed item carries an
``extra`` line of the form ``rkb:sha256 <hash>`` so it is traceable back to the
canonical file and can be reconciled on a later run.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from rkb.collection.catalog import Catalog

# CrossRef-style doc_type -> Zotero itemType.
_DOC_TYPE_TO_ITEM_TYPE = {
    "journal-article": "journalArticle",
    "proceedings-article": "conferencePaper",
    "preprint": "preprint",
    "book": "book",
    "book-chapter": "bookSection",
    "report": "report",
    "thesis": "thesis",
}
_DEFAULT_ITEM_TYPE = "journalArticle"

# Which Zotero field holds the "journal"/venue string for a given itemType.
# Item types not listed here (book, report, thesis) have no natural venue field,
# so the journal value is simply omitted rather than forced into a wrong slot.
_VENUE_FIELD_BY_ITEM_TYPE = {
    "journalArticle": "publicationTitle",
    "conferencePaper": "conferenceName",
    "preprint": "repository",
    "bookSection": "bookTitle",
}


@dataclass
class ZoteroPushFailure:
    """Single-document push failure details."""

    content_sha256: str
    error: str


@dataclass
class ZoteroPushSummary:
    """Aggregate zotero-push results suitable for CLI reporting."""

    pushed: int = 0
    skipped_no_metadata: int = 0
    failed: int = 0
    aborted_rate_limited: bool = False
    failures: list[ZoteroPushFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert summary to a JSON-serializable dictionary."""
        return {
            "pushed": self.pushed,
            "skipped_no_metadata": self.skipped_no_metadata,
            "failed": self.failed,
            "aborted_rate_limited": self.aborted_rate_limited,
            "failures": [asdict(failure) for failure in self.failures],
        }

    def exit_code(self) -> int:
        """Return CLI exit code: 0 ok, 2 on any failure or rate-limit abort."""
        return 2 if (self.failed > 0 or self.aborted_rate_limited) else 0


def build_zotero_item(metadata: dict, content_sha256: str) -> dict:
    """Build a Zotero item dict from resolved catalog metadata.

    Creators use single-field ``name`` mode to avoid mangling names into bad
    first/last splits. The ``extra`` line embeds the content hash for tracing.
    """
    item_type = _DOC_TYPE_TO_ITEM_TYPE.get(metadata.get("doc_type"), _DEFAULT_ITEM_TYPE)

    item: dict = {
        "itemType": item_type,
        "title": metadata.get("title") or "",
        "abstractNote": metadata.get("abstract") or "",
        "extra": f"rkb:sha256 {content_sha256}",
    }

    year = metadata.get("year")
    if year:
        item["date"] = str(year)

    journal = metadata.get("journal")
    venue_field = _VENUE_FIELD_BY_ITEM_TYPE.get(item_type)
    if journal and venue_field:
        item[venue_field] = journal

    authors = metadata.get("authors") or []
    item["creators"] = [
        {"creatorType": "author", "name": author} for author in authors if author
    ]

    return item


def _extract_item_key(response: dict) -> str | None:
    """Parse the created item key from a pyzotero create_items response.

    Handles both the ``{"successful": {"0": {"key": ...}}}`` shape and the
    older ``{"success": {"0": "KEY"}}`` shape.
    """
    if not isinstance(response, dict):
        return None

    successful = response.get("successful")
    if isinstance(successful, dict):
        first = successful.get("0")
        if isinstance(first, dict) and first.get("key"):
            return first["key"]

    success = response.get("success")
    if isinstance(success, dict) and success.get("0"):
        return success["0"]

    return None


def _extract_attachment_key(response: dict) -> str | None:
    """Parse the attachment key from a pyzotero attachment_simple response."""
    if not isinstance(response, dict):
        return None

    successful = response.get("successful")
    if isinstance(successful, dict):
        first = successful.get("0")
        if isinstance(first, dict) and first.get("key"):
            return first["key"]

    success = response.get("success")
    if isinstance(success, dict) and success.get("0"):
        return success["0"]

    return None


def _is_rate_limited_error(error: Exception) -> bool:
    """Return True if the error looks like an HTTP 429 rate-limit response."""
    if "429" in str(error).lower():
        return True

    if getattr(error, "status", None) == 429:
        return True

    response = getattr(error, "response", None)
    return response is not None and getattr(response, "status_code", None) == 429


def _retry_after_seconds(error: Exception) -> float | None:
    """Best-effort read of an explicit Retry-After/backoff seconds header."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _call_with_rate_limit_retry(
    func: Callable[[], object],
    *,
    max_retries: int,
    base_backoff_seconds: float,
    sleep_func: Callable[[float], None],
) -> tuple[str, object]:
    """Invoke ``func`` retrying on 429 with exponential backoff.

    Returns ``("ok", value)`` on success, ``("rate_limited", message)`` if the
    429 persisted past ``max_retries``, or ``("failed", message)`` for any other
    error. Explicit ``Retry-After`` headers take precedence over the computed
    backoff when present.
    """
    retries = 0
    while True:
        try:
            return "ok", func()
        except Exception as error:  # noqa: BLE001 - classified below
            if _is_rate_limited_error(error):
                if retries < max_retries:
                    retries += 1
                    delay = _retry_after_seconds(error)
                    if delay is None:
                        delay = base_backoff_seconds * (2 ** (retries - 1))
                    sleep_func(delay)
                    continue
                return "rate_limited", str(error)
            return "failed", str(error)


def _mark_failed(catalog: Catalog, content_sha256: str, message: str) -> None:
    catalog.set_zotero_link(content_sha256, None, "failed", error_message=message)
    catalog.log_action(content_sha256, "failed", detail=f"zotero push error: {message}")


def _push_one(
    catalog: Catalog,
    zot: object,
    content_sha256: str,
    *,
    max_retries: int,
    base_backoff_seconds: float,
    sleep_func: Callable[[float], None],
) -> tuple[str, str | None]:
    """Push a single document. Returns (outcome, message).

    outcome is one of ``"pushed"``, ``"failed"``, ``"rate_limited"``. On a
    non-rate-limit failure the catalog row is marked failed here; the caller
    owns catalog bookkeeping for the rate-limit case (so abort logic controls it).
    """
    metadata = catalog.get_resolved_metadata(content_sha256)
    if not metadata or not (metadata.get("title") or "").strip():
        message = "no resolved metadata title"
        _mark_failed(catalog, content_sha256, message)
        return "failed", message

    canonical = catalog.get_canonical_file(content_sha256)
    if canonical is None:
        message = "canonical file row missing"
        _mark_failed(catalog, content_sha256, message)
        return "failed", message

    pdf_path = Path(canonical["canonical_path"])
    if not pdf_path.exists():
        message = f"canonical file not found: {pdf_path}"
        _mark_failed(catalog, content_sha256, message)
        return "failed", message

    item = build_zotero_item(metadata, content_sha256)

    status, response = _call_with_rate_limit_retry(
        lambda: zot.create_items([item]),  # type: ignore[attr-defined]
        max_retries=max_retries,
        base_backoff_seconds=base_backoff_seconds,
        sleep_func=sleep_func,
    )
    if status == "rate_limited":
        return "rate_limited", str(response)
    if status == "failed":
        _mark_failed(catalog, content_sha256, str(response))
        return "failed", str(response)

    item_key = _extract_item_key(response)  # type: ignore[arg-type]
    if not item_key:
        message = f"could not parse item key from response: {response!r}"
        _mark_failed(catalog, content_sha256, message)
        return "failed", message

    status, att_response = _call_with_rate_limit_retry(
        lambda: zot.attachment_simple([str(pdf_path)], item_key),  # type: ignore[attr-defined]
        max_retries=max_retries,
        base_backoff_seconds=base_backoff_seconds,
        sleep_func=sleep_func,
    )
    if status == "rate_limited":
        return "rate_limited", str(att_response)
    if status == "failed":
        message = f"item created ({item_key}) but attachment failed: {att_response}"
        _mark_failed(catalog, content_sha256, message)
        return "failed", message

    attachment_key = _extract_attachment_key(att_response)  # type: ignore[arg-type]
    catalog.set_zotero_link(
        content_sha256, item_key, "imported", zotero_attachment_key=attachment_key
    )
    catalog.log_action(
        content_sha256,
        "zotero_pushed",
        source_path=str(pdf_path),
        detail=f"item={item_key} attachment={attachment_key}",
    )
    return "pushed", None


def select_push_candidates(catalog: Catalog) -> tuple[list[dict], int]:
    """Partition unlinked candidates into pushable rows and untitled skips.

    Returns ``(titled_rows, skipped_no_metadata_count)``. ``titled_rows`` keep
    the newest-first ordering from the catalog query.
    """
    titled: list[dict] = []
    skipped = 0
    for row in catalog.get_zotero_push_candidates():
        title = row.get("title")
        if not title or not str(title).strip():
            skipped += 1
            continue
        titled.append(row)
    return titled, skipped


def push_batch_to_zotero(
    catalog: Catalog,
    zot: object,
    *,
    limit: int = 50,
    max_retries: int = 3,
    base_backoff_seconds: float = 1.0,
    sleep_func: Callable[[float], None] = time.sleep,
    progress_callback: Callable[[dict], None] | None = None,
) -> ZoteroPushSummary:
    """Push up to ``limit`` newly resolved catalog items into Zotero.

    Documents without a resolved title are never pushed; they are counted as
    ``skipped_no_metadata``. On a persistent 429 (the same document exhausting
    its retries twice in a row) the whole run aborts so the remaining items are
    left for the next run.
    """
    summary = ZoteroPushSummary()
    titled, summary.skipped_no_metadata = select_push_candidates(catalog)

    to_push = [row["content_sha256"] for row in titled[: max(0, int(limit))]]

    index = 0
    pending_rate_limited: str | None = None
    while index < len(to_push):
        content_sha256 = to_push[index]
        outcome, message = _push_one(
            catalog,
            zot,
            content_sha256,
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            sleep_func=sleep_func,
        )

        if outcome == "pushed":
            summary.pushed += 1
            pending_rate_limited = None
            index += 1
        elif outcome == "failed":
            summary.failed += 1
            summary.failures.append(ZoteroPushFailure(content_sha256, message or "unknown error"))
            pending_rate_limited = None
            index += 1
        else:  # rate_limited
            _mark_failed(catalog, content_sha256, message or "rate limited")
            if pending_rate_limited == content_sha256:
                # Same document rate-limited twice in a row after full retries:
                # the API is telling us to stop. Abort and leave the rest.
                summary.failed += 1
                summary.failures.append(
                    ZoteroPushFailure(
                        content_sha256,
                        f"persistent rate limit; aborting run: {message}",
                    )
                )
                summary.aborted_rate_limited = True
                break
            # First rate-limit exhaustion for this hash: retry the same hash once
            # more (do not advance) to confirm the limit is persistent.
            pending_rate_limited = content_sha256

        if progress_callback:
            progress_callback({"hash": content_sha256, "status": outcome})

    return summary
