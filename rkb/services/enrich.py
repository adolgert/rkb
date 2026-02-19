"""Enrich canonical collection with resolved metadata and rename PDFs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import rename_pdf
from rkb.collection.catalog import Catalog
from rkb.collection.display_name import generate_display_name

if TYPE_CHECKING:
    from rkb.collection.config import CollectionConfig
    from rkb.services.metadata_resolver import MetadataResolver

logger = logging.getLogger(__name__)

_PROGRESS_THRESHOLD = 10


@dataclass
class EnrichFailure:
    """Single-file enrichment failure details."""

    content_sha256: str
    error: str


@dataclass
class EnrichSummary:
    """Aggregate enrichment results suitable for CLI reporting."""

    total: int = 0
    resolved: int = 0
    renamed: int = 0
    already_resolved: int = 0
    failed: int = 0
    failures: list[EnrichFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "total": self.total,
            "resolved": self.resolved,
            "renamed": self.renamed,
            "already_resolved": self.already_resolved,
            "failed": self.failed,
            "failures": [
                {"content_sha256": f.content_sha256, "error": f.error}
                for f in self.failures
            ],
        }

    def exit_code(self) -> int:
        """Return CLI exit code: 2 if any failures, else 0."""
        return 2 if self.failed > 0 else 0


def _iter_with_progress(items: list[str], description: str):
    if len(items) <= _PROGRESS_THRESHOLD:
        return items
    try:
        from tqdm import tqdm
    except ImportError:
        return items
    return tqdm(items, desc=description, unit="file")


def enrich_collection(
    config: CollectionConfig,
    resolver: MetadataResolver,
    *,
    force: bool = False,
    hashes: list[str] | None = None,
    rename: bool = True,
    dry_run: bool = False,
) -> EnrichSummary:
    """Resolve metadata for papers and optionally rename PDFs.

    Args:
        config: Collection configuration with library_root and catalog_db.
        resolver: MetadataResolver instance for extraction and merging.
        force: Re-resolve even if metadata is already cached.
        hashes: Specific hashes to process. None means all unresolved.
        rename: Whether to rename PDFs based on resolved metadata.
        dry_run: Report what would happen without modifying files or database.
    """
    catalog = Catalog(config.catalog_db)
    catalog.initialize()
    summary = EnrichSummary()

    try:
        target_hashes = hashes if hashes is not None else catalog.get_unresolved_hashes()
        summary.total = len(target_hashes)

        for content_sha256 in _iter_with_progress(target_hashes, "Enriching"):
            try:
                _enrich_one(
                    content_sha256,
                    catalog=catalog,
                    config=config,
                    resolver=resolver,
                    summary=summary,
                    force=force,
                    rename=rename,
                    dry_run=dry_run,
                )
            except Exception as exc:
                summary.failed += 1
                summary.failures.append(
                    EnrichFailure(content_sha256=content_sha256, error=str(exc))
                )
                logger.debug("Enrich failed for %s: %s", content_sha256[:12], exc)
    finally:
        catalog.close()

    return summary


def _enrich_one(
    content_sha256: str,
    *,
    catalog: Catalog,
    config: CollectionConfig,
    resolver: MetadataResolver,
    summary: EnrichSummary,
    force: bool,
    rename: bool,
    dry_run: bool,
) -> None:
    """Resolve metadata and optionally rename one PDF."""
    row = catalog.get_canonical_file(content_sha256)
    if row is None:
        msg = "not found in catalog"
        raise FileNotFoundError(msg)

    pdf_path = Path(row["canonical_path"])

    if dry_run:
        cached = catalog.get_resolved_metadata(content_sha256)
        if cached is not None and not force:
            summary.already_resolved += 1
        else:
            summary.resolved += 1
        return

    result = resolver.resolve(pdf_path, content_sha256, force=force)

    if result.cached and not force:
        summary.already_resolved += 1
        return

    summary.resolved += 1

    if rename and result.title:
        first_author = result.authors[0] if result.authors else None
        metadata = {
            "author": first_author,
            "year": result.year,
            "title": result.title,
        }
        new_display = generate_display_name(pdf_path, metadata=metadata)
        new_path = rename_pdf(config.library_root, content_sha256, new_display)
        catalog.update_display_name(
            content_sha256, new_path.name, str(new_path)
        )
        catalog.log_action(
            content_sha256,
            "enriched_rename",
            detail=f"renamed to {new_path.name}",
        )
        summary.renamed += 1
        logger.info("Renamed %s -> %s", content_sha256[:12], new_path.name)
