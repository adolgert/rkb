"""Ingest command - Scan directories and ingest PDFs into canonical collection."""
# ruff: noqa: T201

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rkb.collection.config import CollectionConfig
from rkb.collection.ingest import ingest_directories


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "directories",
        nargs="+",
        type=Path,
        metavar="DIRECTORY",
        help="One or more directories to scan recursively for PDFs",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without copying or database updates",
    )

    parser.add_argument(
        "--skip-zotero",
        action="store_true",
        default=True,
        help="Skip Zotero import step (default in Phase 2a)",
    )

    parser.add_argument(
        "--with-zotero",
        action="store_false",
        dest="skip_zotero",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--no-display-name",
        action="store_true",
        help="Use original filename instead of generated display name",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _print_human_summary(summary: dict) -> None:
    print(f"Scanned: {summary['scanned']} files")
    print(f"  New:         {summary['new']}")
    print(f"  Duplicate:   {summary['duplicate']}")
    print(f"  Failed:      {summary['failed']}")
    print()
    print("Zotero:")
    print(f"  Already there: {summary['zotero_existing']}")
    print(f"  Imported:      {summary['zotero_imported']}")

    if summary["failures"]:
        print()
        print("Failures:")
        for failure in summary["failures"]:
            print(f"  {failure['path']} -- {failure['error']}")


def execute(args: argparse.Namespace) -> int:
    """Execute the ingest command."""
    try:
        config = CollectionConfig.load(config_path=args.config)

        if not args.skip_zotero:
            print(
                "Warning: Zotero import is not implemented in Phase 2a; "
                "continuing with canonical ingest only."
            )

        summary = ingest_directories(
            directories=args.directories,
            config=config,
            dry_run=args.dry_run,
            skip_zotero=True,
            no_display_name=args.no_display_name,
        )

        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_human_summary(summary.to_dict())

        return summary.exit_code()
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as error:
        print(f"Ingest failed: {error}")
        return 1
    except Exception as error:
        print(f"Ingest failed: {error}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

