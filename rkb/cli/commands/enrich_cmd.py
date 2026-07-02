"""Enrich command - Resolve metadata and rename PDFs in canonical collection."""
# ruff: noqa: T201

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from rkb.collection.config import CollectionConfig
from rkb.services.enrich import enrich_collection

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-resolve metadata even for already-resolved papers",
    )
    parser.add_argument(
        "--no-rename",
        action="store_true",
        help="Resolve metadata but do not rename PDF files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without modifying files or database",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _build_resolver(config: CollectionConfig):
    from rkb.collection.catalog import Catalog
    from rkb.services.metadata_resolver import MetadataResolver

    catalog = Catalog(config.catalog_db)
    catalog.initialize()
    return MetadataResolver(
        catalog,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        s2_api_key=os.environ.get("S2_API_KEY"),
    ), catalog


def _print_human_summary(summary_dict: dict) -> None:
    print(f"Total:            {summary_dict['total']}")
    print(f"  Resolved:       {summary_dict['resolved']}")
    print(f"  Nothing found:  {summary_dict['nothing_found']}")
    print(f"  Renamed:        {summary_dict['renamed']}")
    print(f"  Already done:   {summary_dict['already_resolved']}")
    print(f"  Failed:         {summary_dict['failed']}")

    if summary_dict["failures"]:
        print()
        print("Failures:")
        for failure in summary_dict["failures"]:
            print(f"  {failure['content_sha256'][:12]}... -- {failure['error']}")


def execute(args: argparse.Namespace) -> int:
    """Execute the enrich command."""
    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))
        resolver, resolver_catalog = _build_resolver(config)

        try:
            summary = enrich_collection(
                config,
                resolver,
                force=args.force,
                rename=not args.no_rename,
                dry_run=args.dry_run,
            )
        finally:
            resolver_catalog.close()

        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_human_summary(summary.to_dict())

        return summary.exit_code()
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as error:
        print(f"Enrich failed: {error}")
        return 1
    except Exception as error:
        print(f"Enrich failed: {error}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return 1
