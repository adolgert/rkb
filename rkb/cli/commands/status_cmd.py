"""Status command - report collection and ingest health."""
# ruff: noqa: T201

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=10,
        help="Number of recent ingest log entries to show (default: 10)",
    )


def _human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _empty_status(config: CollectionConfig, recent_limit: int) -> dict:
    return {
        "library_root": str(config.library_root),
        "catalog_db": str(config.catalog_db),
        "canonical_files": 0,
        "canonical_store_bytes": 0,
        "zotero_linked_files": 0,
        "unlinked_files": 0,
        "recent_ingest": [],
        "recent_limit": recent_limit,
    }


def _collect_status(config: CollectionConfig, recent_limit: int) -> dict:
    if not config.catalog_db.exists():
        return _empty_status(config, recent_limit)

    catalog = Catalog(config.catalog_db)
    try:
        stats = catalog.get_statistics()
        recent = catalog.get_recent_ingest_log(limit=recent_limit)
        return {
            "library_root": str(config.library_root),
            "catalog_db": str(config.catalog_db),
            "canonical_files": stats["canonical_files"],
            "canonical_store_bytes": catalog.get_canonical_store_bytes(),
            "zotero_linked_files": catalog.get_zotero_linked_count(),
            "unlinked_files": stats["unlinked_to_zotero"],
            "recent_ingest": recent,
            "recent_limit": recent_limit,
        }
    except sqlite3.OperationalError:
        return _empty_status(config, recent_limit)
    finally:
        catalog.close()


def _print_human_status(payload: dict) -> None:
    print("Collection Status:")
    print(f"  Library root: {payload['library_root']}")
    print(f"  Catalog DB:   {payload['catalog_db']}")
    print()
    print("Canonical Store:")
    print(f"  Files: {payload['canonical_files']}")
    bytes_count = payload["canonical_store_bytes"]
    print(
        f"  Size:  {bytes_count} bytes "
        f"({_human_bytes(bytes_count)})"
    )
    print()
    print("Zotero Coverage:")
    print(f"  Linked files:   {payload['zotero_linked_files']}")
    print(f"  Unlinked files: {payload['unlinked_files']}")
    print()
    print(f"Recent ingest activity (latest {payload['recent_limit']}):")
    if not payload["recent_ingest"]:
        print("  None")
        return

    for row in payload["recent_ingest"]:
        content_short = row["content_sha256"][:12]
        source = row["source_path"] or "-"
        detail = row["detail"] or "-"
        print(
            f"  {row['timestamp']}  {row['action']}  {content_short}  "
            f"source={source}  detail={detail}"
        )


def execute(args: argparse.Namespace) -> int:
    """Execute the status command."""
    try:
        config = CollectionConfig.load(config_path=args.config)
        recent_limit = max(1, int(args.recent))
        payload = _collect_status(config, recent_limit)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            _print_human_status(payload)
        return 0
    except Exception as error:
        print(f"Status failed: {error}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1
