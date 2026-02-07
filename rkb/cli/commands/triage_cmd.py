"""Triage command - Launch local work-side PDF triage app."""
# ruff: noqa: T201

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.config import CollectionConfig
from rkb.triage.app import create_app
from rkb.triage.decisions import TriageDecisionStore
from rkb.triage.staging import rebuild_staging

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for Flask app (default: 5000)",
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        help="Downloads directory to scan (default from config)",
    )
    parser.add_argument(
        "--staging",
        type=Path,
        help="Staging directory (default from config)",
    )
    parser.add_argument(
        "--rebuild-staging",
        action="store_true",
        help="Rebuild staging directory from triage decisions and exit",
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the triage command."""
    try:
        config = CollectionConfig.load(config_path=args.config)
        downloads_dir = (args.downloads or config.work_downloads).expanduser()
        staging_dir = (args.staging or config.box_staging).expanduser()
        db_path = staging_dir / "triage.db"

        if args.rebuild_staging:
            store = TriageDecisionStore(db_path)
            store.initialize()
            summary = rebuild_staging(staging_dir, store)
            store.close()
            print("Rebuild complete")
            print(f"  Re-staged:      {summary['re_staged']}")
            print(f"  Missing source: {summary['missing_source']}")
            return 0

        app = create_app(downloads_dir=downloads_dir, staging_dir=staging_dir, db_path=db_path)
        print(f"Triage app running at http://127.0.0.1:{args.port}")
        app.run(host="127.0.0.1", port=args.port, debug=False)
        return 0
    except Exception as error:
        print(f"Triage failed: {error}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1
