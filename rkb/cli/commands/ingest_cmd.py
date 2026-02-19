"""Ingest command - Scan directories and ingest PDFs into canonical collection."""
# ruff: noqa: T201

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.config import CollectionConfig
from rkb.collection.ingest import ingest_directories

if TYPE_CHECKING:
    import argparse


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
        "--zotero",
        action="store_true",
        default=False,
        help="Enable Zotero import step (off by default)",
    )

    parser.add_argument(
        "--no-display-name",
        action="store_true",
        help="Use original filename instead of generated display name",
    )

    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Run metadata resolution and rename for newly ingested PDFs",
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


def _run_enrich_for_hashes(
    config: CollectionConfig,
    new_hashes: list[str],
    *,
    dry_run: bool,
    use_json: bool,
) -> int:
    """Resolve metadata for newly ingested hashes."""
    import os

    from rkb.collection.catalog import Catalog
    from rkb.services.enrich import enrich_collection
    from rkb.services.metadata_resolver import MetadataResolver

    catalog = Catalog(config.catalog_db)
    catalog.initialize()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    resolver = MetadataResolver(catalog, anthropic_api_key=api_key)

    try:
        enrich_summary = enrich_collection(
            config, resolver, hashes=new_hashes, dry_run=dry_run,
        )
    finally:
        catalog.close()

    if use_json:
        print(json.dumps(enrich_summary.to_dict(), indent=2))
    else:
        print()
        print("Enrich:")
        print(f"  Resolved:     {enrich_summary.resolved}")
        print(f"  Renamed:      {enrich_summary.renamed}")
        print(f"  Failed:       {enrich_summary.failed}")

    return enrich_summary.exit_code()


def execute(args: argparse.Namespace) -> int:
    """Execute the ingest command."""
    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))

        summary = ingest_directories(
            directories=args.directories,
            config=config,
            dry_run=args.dry_run,
            skip_zotero=not args.zotero,
            no_display_name=args.no_display_name,
        )

        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_human_summary(summary.to_dict())

        exit_code = summary.exit_code()

        if args.resolve and summary.new_hashes:
            enrich_exit = _run_enrich_for_hashes(
                config,
                summary.new_hashes,
                dry_run=args.dry_run,
                use_json=args.json,
            )
            exit_code = max(exit_code, enrich_exit)

        return exit_code
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as error:
        print(f"Ingest failed: {error}")
        return 1
    except Exception as error:
        print(f"Ingest failed: {error}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return 1
