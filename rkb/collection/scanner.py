"""PDF discovery utilities for ingest workflows."""

from __future__ import annotations

import os
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
        if not os.access(expanded, os.R_OK | os.X_OK):
            raise PermissionError(expanded)

        try:
            with os.scandir(expanded):
                pass
        except PermissionError:
            raise PermissionError(expanded) from None

        for root, _dirs, files in os.walk(expanded, onerror=lambda _error: None):
            root_path = Path(root)
            for filename in files:
                if not filename.lower().endswith(".pdf"):
                    continue

                candidate = root_path / filename
                try:
                    resolved = candidate.resolve()
                    if resolved in seen:
                        continue
                    if not resolved.is_file():
                        continue
                except OSError:
                    continue

                seen.add(resolved)
                discovered.append(resolved)

    return sorted(discovered, key=str)
