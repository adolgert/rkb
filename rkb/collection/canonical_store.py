"""Content-addressed canonical store management."""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

from rkb.collection.hashing import hash_file_sha256

if TYPE_CHECKING:
    from pathlib import Path

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _normalize_sha256(content_sha256: str) -> str:
    normalized = content_sha256.lower()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise ValueError("content_sha256 must be a 64-character hexadecimal SHA-256 hash")
    return normalized


def canonical_dir(library_root: Path, content_sha256: str) -> Path:
    """Return canonical hash directory: root/sha256/ab/cd/fullhash."""
    normalized = _normalize_sha256(content_sha256)
    return library_root / "sha256" / normalized[:2] / normalized[2:4] / normalized


def _existing_pdf(hash_dir: Path) -> Path | None:
    pdf_files = sorted(
        path for path in hash_dir.iterdir() if path.is_file() and path.suffix == ".pdf"
    )
    if len(pdf_files) > 1:
        raise RuntimeError(
            f"Canonical directory must contain one PDF, found {len(pdf_files)}: {hash_dir}"
        )
    return pdf_files[0] if pdf_files else None


def is_stored(library_root: Path, content_sha256: str) -> bool:
    """Return True if the canonical hash directory already contains a PDF."""
    hash_dir = canonical_dir(library_root, content_sha256)
    if not hash_dir.exists():
        return False
    return _existing_pdf(hash_dir) is not None


def store_pdf(
    library_root: Path,
    source_path: Path,
    content_sha256: str,
    display_name: str,
) -> Path:
    """Copy a PDF into canonical storage and verify byte-level integrity."""
    normalized = _normalize_sha256(content_sha256)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not source_path.is_file():
        raise ValueError(f"Expected source_path to be a file: {source_path}")

    source_hash = hash_file_sha256(source_path)
    if source_hash != normalized:
        raise ValueError("Provided content_sha256 does not match source file bytes")

    hash_dir = canonical_dir(library_root, normalized)
    hash_dir.mkdir(parents=True, exist_ok=True)

    existing_pdf = _existing_pdf(hash_dir)
    if existing_pdf is not None:
        existing_hash = hash_file_sha256(existing_pdf)
        if existing_hash != normalized:
            raise RuntimeError(
                "Existing canonical file hash mismatch for "
                f"{existing_pdf}: expected {normalized}, got {existing_hash}"
            )
        return existing_pdf

    destination_name = (
        display_name if display_name.lower().endswith(".pdf") else f"{display_name}.pdf"
    )
    destination_path = hash_dir / destination_name
    shutil.copy2(source_path, destination_path)

    destination_hash = hash_file_sha256(destination_path)
    if destination_hash != normalized:
        destination_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Copied file hash mismatch for "
            f"{destination_path}: expected {normalized}, got {destination_hash}"
        )

    return destination_path
