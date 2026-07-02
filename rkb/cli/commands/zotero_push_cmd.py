"""Zotero-push command - Push resolved catalog items to Zotero as items with attachments."""
# ruff: noqa: T201

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig

if TYPE_CHECKING:
    import argparse

DEFAULT_LIMIT = 50
_PREVIEW_COUNT = 10


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"Maximum items to push in one run (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be pushed without contacting Zotero",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _run_dry_run(catalog: Catalog, args: argparse.Namespace) -> int:
    from rkb.collection.zotero_push import select_push_candidates

    titled, skipped = select_push_candidates(catalog)
    capped = titled[: max(0, int(args.limit))]
    preview = [row["title"] or row["display_name"] for row in capped[:_PREVIEW_COUNT]]

    if args.json:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "would_push": len(capped),
                    "eligible": len(titled),
                    "skipped_no_metadata": skipped,
                    "preview": preview,
                },
                indent=2,
            )
        )
        return 0

    print(f"Would push {len(capped)} item(s) to Zotero (of {len(titled)} eligible, newest first).")
    print(f"Skipped (no resolved title): {skipped}")
    for name in preview:
        print(f"  - {name}")
    if len(capped) > len(preview):
        print(f"  ... and {len(capped) - len(preview)} more")
    if skipped:
        print("Hint: run `rkb enrich` to resolve metadata for skipped documents.")
    return 0


def _print_summary(summary) -> None:  # noqa: ANN001 - ZoteroPushSummary
    print(f"Pushed:                {summary.pushed}")
    print(f"Skipped (no title):    {summary.skipped_no_metadata}")
    print(f"Failed:                {summary.failed}")
    if summary.aborted_rate_limited:
        print(
            "Aborted: Zotero rate limit persisted. "
            "Remaining items will be pushed on the next run."
        )
    if summary.skipped_no_metadata:
        print("Hint: run `rkb enrich` to resolve metadata for skipped documents.")
    if summary.failures:
        print("Failures:")
        for failure in summary.failures:
            print(f"  {failure.content_sha256[:12]} -- {failure.error}")


def execute(args: argparse.Namespace) -> int:
    """Execute the zotero-push command."""
    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))
        with Catalog(config.catalog_db) as catalog:
            catalog.initialize()

            if args.dry_run:
                return _run_dry_run(catalog, args)

            from rkb.collection.runtime import build_zotero_client
            from rkb.collection.zotero_push import push_batch_to_zotero

            zot = build_zotero_client(config)
            summary = push_batch_to_zotero(catalog, zot, limit=args.limit)

        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_summary(summary)

        return summary.exit_code()
    except Exception as error:
        print(f"Zotero push failed: {error}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return 1
