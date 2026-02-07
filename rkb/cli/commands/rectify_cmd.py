"""Rectify command - Reconcile scattered PDFs with canonical and Zotero state."""
# ruff: noqa: T201

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.config import CollectionConfig
from rkb.collection.rectify import rectify_collection

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--scan",
        nargs="+",
        required=True,
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
        "--report",
        action="store_true",
        help="Gap analysis only (no copies or Zotero API calls)",
    )
    parser.add_argument(
        "--skip-zotero",
        action="store_true",
        default=False,
        help="Only ensure canonical-store completeness; skip Zotero import",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _print_human_summary(summary: dict) -> None:
    print("Discovery:")
    print(f"  Scanned directories: {summary['scanned_directories']}")
    print(f"  Total PDF files found: {summary['total_files_found']}")
    print(f"  Unique PDFs (by hash): {summary['unique_pdfs']}")
    print(f"  Duplicate files: {summary['duplicate_files']}")
    print()
    print("Canonical Store:")
    print(f"  Already in store: {summary['canonical_already']}")
    print(f"  New (will copy): {summary['canonical_new']}")
    print()
    print("Zotero:")
    print(f"  Already in Zotero: {summary['zotero_existing']}")
    print(f"  Not in Zotero (will import): {summary['zotero_to_import']}")
    print(f"  In Zotero but not in store: {summary['zotero_reverse_missing_store']}")
    print()
    print("Actions taken:")
    print(f"  Copied to canonical store: {summary['copied_to_canonical']}")
    print(f"  Imported to Zotero: {summary['imported_to_zotero']}")
    print(f"  Failures: {summary['failed']}")
    if summary["failures"]:
        print()
        print("Failures:")
        for failure in summary["failures"]:
            print(f"  {failure['path']} -- {failure['error']}")


def execute(args: argparse.Namespace) -> int:
    """Execute the rectify command."""
    try:
        config = CollectionConfig.load(config_path=args.config)
        summary = rectify_collection(
            scan_directories=args.scan,
            config=config,
            dry_run=args.dry_run,
            report=args.report,
            skip_zotero=args.skip_zotero,
        )

        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_human_summary(summary.to_dict())
        return summary.exit_code()
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as error:
        print(f"Rectify failed: {error}")
        return 1
    except Exception as error:
        print(f"Rectify failed: {error}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1
