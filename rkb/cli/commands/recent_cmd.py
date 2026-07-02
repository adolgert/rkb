"""Recent command - List recently imported PDFs in reverse-chronological order."""
# ruff: noqa: T201

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import quote

from rkb.collection.canonical_store import find_extraction
from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig

if TYPE_CHECKING:
    import argparse

DEFAULT_LIMIT = 20


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"Number of documents to list (default: {DEFAULT_LIMIT})",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _local_timestamp(iso_utc: str) -> str:
    """Convert a stored ISO-8601 UTC timestamp to local time for display."""
    try:
        return datetime.fromisoformat(iso_utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_utc


def _display_entries(entries: list[dict]) -> None:
    if not entries:
        print("No documents in the catalog yet.")
        return

    print(f"📚 {len(entries)} most recently imported documents (newest first)")
    print("=" * 80)
    for i, entry in enumerate(entries, 1):
        title = entry["title"] or entry["display_name"]
        print(f"\n{i:>3}. {_local_timestamp(entry['ingested_at'])}  {title}")

        details = []
        if entry["authors"]:
            authors = entry["authors"]
            suffix = " et al." if len(authors) > 3 else ""
            details.append(", ".join(authors[:3]) + suffix)
        if entry["year"]:
            details.append(str(entry["year"]))
        if entry["journal"]:
            details.append(entry["journal"])
        if details:
            print(f"     {' | '.join(details)}")

        pdf_link = f"file://{quote(entry['canonical_path'], safe='/')}"
        print(f"     🔗 PDF:      {pdf_link}")
        if entry["extraction_path"]:
            print(f"     📝 Markdown: {entry['extraction_path']}")
        else:
            print("     📝 Markdown: (not translated yet)")


def execute(args: argparse.Namespace) -> int:
    """Execute the recent command."""
    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))
        with Catalog(config.catalog_db) as catalog:
            catalog.initialize()
            entries = catalog.list_recent_canonical_files(limit=args.limit)

        for entry in entries:
            extraction = find_extraction(config.library_root, entry["content_sha256"])
            entry["extraction_path"] = str(extraction) if extraction else None
            entry.pop("authors_json", None)

        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            _display_entries(entries)

        return 0
    except Exception as error:
        print(f"Recent failed: {error}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return 1
