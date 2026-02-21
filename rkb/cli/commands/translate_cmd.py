"""Translate command - Convert PDFs to Markdown using marker-pdf."""
# ruff: noqa: T201

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from rkb.collection.config import CollectionConfig
from rkb.services.translate import (
    DEFAULT_CHUNK_PAGES,
    marker_pdf_version,
    tool_subdir,
    translate_collection,
)

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Translate every PDF, even those that already have a nougat extraction. "
            "By default only PDFs with no extraction at all are processed."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many PDFs would be translated without running marker-pdf",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
        metavar="MODEL",
        help="Gemini model name for LLM-assisted extraction (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--chunk-pages",
        type=int,
        default=DEFAULT_CHUNK_PAGES,
        metavar="N",
        help=f"Max pages per conversion chunk for large PDFs (default: {DEFAULT_CHUNK_PAGES})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )


def _print_human_summary(summary_dict: dict, *, dry_run: bool, subdir: str) -> None:
    verb = "Would translate" if dry_run else "Translated"
    print(f"Tool:             {subdir}")
    print(f"Total found:      {summary_dict['total']}")
    print(f"{verb}:      {summary_dict['translated'] if not dry_run else summary_dict['skipped']}")
    if not dry_run:
        print(f"  Failed:         {summary_dict['failed']}")
    if summary_dict["failures"]:
        print()
        print("Failures:")
        for f in summary_dict["failures"]:
            print(f"  {f['content_sha256'][:12]}...  {f['error']}")


def execute(args: argparse.Namespace) -> int:
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_api_key and not args.dry_run:
        print("Error: GEMINI_API_KEY environment variable is not set")
        return 1

    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))
        version = marker_pdf_version()
        subdir = tool_subdir(version)

        if args.dry_run:
            # Avoid importing marker models for a dry run
            from rkb.services.translate import _find_pdfs_to_translate
            pdfs = _find_pdfs_to_translate(config.library_root, all_pdfs=args.all, subdir=subdir)
            summary_dict = {
                "total": len(pdfs),
                "translated": 0,
                "skipped": len(pdfs),
                "failed": 0,
                "failures": [],
            }
            if getattr(args, "json", False):
                print(json.dumps(summary_dict, indent=2))
            else:
                _print_human_summary(summary_dict, dry_run=True, subdir=subdir)
            return 0

        summary = translate_collection(
            config,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
            dry_run=False,
            all_pdfs=args.all,
            chunk_pages=args.chunk_pages,
        )

        if getattr(args, "json", False):
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            _print_human_summary(summary.to_dict(), dry_run=False, subdir=subdir)

        return summary.exit_code()

    except (FileNotFoundError, PermissionError, ValueError) as error:
        print(f"Translate failed: {error}")
        return 1
    except Exception as error:
        print(f"Translate failed: {error}")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        return 1
