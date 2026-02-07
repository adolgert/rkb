"""PDF discovery utilities for ingest workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def scan_pdf_files(directories: list[Path]) -> list[Path]:
    """Recursively discover PDF files in one or more directories."""
    if not directories:
        raise ValueError("At least one directory is required")

    discovered: list[Path] = []
    seen: set[Path] = set()

    for directory in directories:
        expanded = directory.expanduser()
        if not expanded.exists():
            raise FileNotFoundError(expanded)
        if not expanded.is_dir():
            raise NotADirectoryError(expanded)

        for candidate in expanded.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() != ".pdf":
                continue

            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(resolved)

    return sorted(discovered, key=str)
