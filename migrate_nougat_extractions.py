#!/usr/bin/env python3
"""Migrate nougat-ocr .mmd extractions to sit beside their PDFs in the canonical store.

Source:  ~/dev/kbase/rkb_extractions/documents/{uuid}/extracted.mmd
Target:  ~/Dropbox/findpdfs-library/sha256/{ab}/{cd}/{hash}/extractions/nougat-ocr-1.0.0/extracted.mmd

Connection: rkb_documents.db joins extractions -> documents via doc_id, giving
content_hash (SHA-256) which matches canonical_files.content_sha256 in pdf_catalog.db.

Usage:
    python migrate_nougat_extractions.py           # dry run, prints what would happen
    python migrate_nougat_extractions.py --execute # actually copy files
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

RKB_DB = Path.home() / "dev/kbase/rkb_documents.db"
LIBRARY_ROOT = Path.home() / "Dropbox/findpdfs-library"
CATALOG_DB = LIBRARY_ROOT / "db/pdf_catalog.db"
TOOL_SUBDIR = "extractions/nougat-ocr-1.0.0"
OUTPUT_FILENAME = "extracted.mmd"


def canonical_dir(sha256: str) -> Path:
    return LIBRARY_ROOT / "sha256" / sha256[:2] / sha256[2:4] / sha256


def load_extraction_map() -> list[tuple[str, Path, str]]:
    """Return [(doc_id, mmd_path, content_sha256), ...] for all nougat extractions."""
    con = sqlite3.connect(RKB_DB)
    rows = con.execute("""
        SELECT e.doc_id, e.extraction_path, d.content_hash
        FROM extractions e
        JOIN documents d USING (doc_id)
        WHERE e.extractor_name = 'nougat'
    """).fetchall()
    con.close()

    result = []
    for doc_id, extraction_path, content_hash in rows:
        mmd_path = Path.home() / "dev/kbase" / extraction_path
        result.append((doc_id, mmd_path, content_hash))
    return result


def load_catalog_hashes() -> set[str]:
    con = sqlite3.connect(CATALOG_DB)
    hashes = {row[0] for row in con.execute("SELECT content_sha256 FROM canonical_files")}
    con.close()
    return hashes


def migrate(*, execute: bool) -> None:
    for path in (RKB_DB, CATALOG_DB):
        if not path.exists():
            sys.exit(f"Required database not found: {path}")

    print(f"{'DRY RUN — ' if not execute else ''}Migrating nougat-ocr-1.0.0 extractions")
    print(f"  Source DB : {RKB_DB}")
    print(f"  Library   : {LIBRARY_ROOT}")
    print()

    extractions = load_extraction_map()
    catalog_hashes = load_catalog_hashes()

    copied = skipped_exists = skipped_no_source = skipped_not_in_catalog = 0

    for doc_id, mmd_path, content_hash in sorted(extractions, key=lambda r: r[0]):
        if not mmd_path.exists():
            print(f"  SKIP (source missing) {mmd_path}")
            skipped_no_source += 1
            continue

        if content_hash not in catalog_hashes:
            print(f"  SKIP (not in catalog) {doc_id}  hash={content_hash[:16]}...")
            skipped_not_in_catalog += 1
            continue

        dest_dir = canonical_dir(content_hash) / TOOL_SUBDIR
        dest_path = dest_dir / OUTPUT_FILENAME

        if dest_path.exists():
            skipped_exists += 1
            continue

        if execute:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mmd_path, dest_path)
        else:
            print(f"  WOULD COPY  .../{content_hash[:8]}.../{TOOL_SUBDIR}/{OUTPUT_FILENAME}")

        copied += 1

    print()
    print(f"{'Would copy' if not execute else 'Copied'}  : {copied}")
    print(f"Already exist     : {skipped_exists}")
    print(f"Source missing    : {skipped_no_source}")
    print(f"Not in catalog    : {skipped_not_in_catalog}")
    print(f"Total extractions : {len(extractions)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--execute", action="store_true", help="Actually copy files (default is dry run)")
    args = parser.parse_args()
    migrate(execute=args.execute)
