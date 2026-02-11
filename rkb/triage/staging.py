"""Staging-directory management for triage approvals."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.hashing import hash_file_sha256

if TYPE_CHECKING:
    from rkb.triage.decisions import TriageDecisionStore


def _resolve_collision_path(staging_dir: Path, original_filename: str, content_sha256: str) -> Path:
    base_name = Path(original_filename).name or f"{content_sha256[:8]}.pdf"
    stem = Path(base_name).stem
    suffix = Path(base_name).suffix or ".pdf"

    candidate = staging_dir / base_name
    if not candidate.exists():
        return candidate

    try:
        if hash_file_sha256(candidate) == content_sha256:
            return candidate
    except Exception:
        pass

    disambiguated = staging_dir / f"{stem}_{content_sha256[:8]}{suffix}"
    if not disambiguated.exists():
        return disambiguated

    try:
        if hash_file_sha256(disambiguated) == content_sha256:
            return disambiguated
    except Exception:
        pass

    counter = 2
    while True:
        fallback = staging_dir / f"{stem}_{content_sha256[:8]}_{counter}{suffix}"
        if not fallback.exists():
            return fallback
        counter += 1


def stage_approved_file(
    source_path: Path,
    original_filename: str,
    content_sha256: str,
    staging_dir: Path,
) -> Path:
    """Copy an approved source PDF into staging with collision-safe naming."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    destination = _resolve_collision_path(staging_dir, original_filename, content_sha256)
    if destination.exists():
        return destination

    shutil.copy2(source_path, destination)
    return destination


def remove_staged_file(staged_path: str | Path | None) -> None:
    """Remove a previously staged PDF path if it exists."""
    if staged_path is None:
        return
    Path(staged_path).unlink(missing_ok=True)


def rebuild_staging(staging_dir: Path, store: TriageDecisionStore) -> dict[str, int]:
    """Reconstruct staging directory from currently approved decisions."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    for staged_pdf in staging_dir.glob("*.pdf"):
        staged_pdf.unlink()

    summary = {"re_staged": 0, "missing_source": 0}
    for row in store.list_approved():
        source_path = Path(row["original_path"])
        if not source_path.exists():
            summary["missing_source"] += 1
            store.update_staged_path(row["content_sha256"], None)
            continue

        staged = stage_approved_file(
            source_path=source_path,
            original_filename=row["original_filename"],
            content_sha256=row["content_sha256"],
            staging_dir=staging_dir,
        )
        store.update_staged_path(row["content_sha256"], str(staged))
        summary["re_staged"] += 1

    return summary

