"""Import command - One-shot pipeline: ingest + enrich, translate, index."""
# ruff: noqa: T201

from __future__ import annotations

import argparse
import os
from pathlib import Path

from rkb.cli.commands import index_cmd, ingest_cmd, translate_cmd

DEFAULT_SOURCE = "~/Dropbox/Mendeley"
ENV_FILE_NAME = "local.env"

# Keys the pipeline needs; loaded from local.env when absent from the environment.
_API_KEYS = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "S2_API_KEY", "GEMINI_MODEL_NAME")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "directories",
        nargs="*",
        type=Path,
        metavar="DIRECTORY",
        help=f"Directories to scan recursively for new PDFs (default: {DEFAULT_SOURCE})",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what each step would do without changing anything",
    )


def _load_env_file(env_path: Path) -> list[str]:
    """Load missing KEY=VALUE pairs from an env file. Returns keys that were set."""
    loaded = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ").strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def _ensure_api_keys() -> None:
    """Load API keys from local.env in the current directory if not already set."""
    if all(key in os.environ for key in _API_KEYS):
        return
    env_path = Path.cwd() / ENV_FILE_NAME
    if env_path.exists():
        loaded = _load_env_file(env_path)
        if loaded:
            print(f"Loaded {', '.join(sorted(loaded))} from {env_path}")
            print()


def _step_namespace(module, argv: list[str], parent: argparse.Namespace) -> argparse.Namespace:
    """Build an argument namespace for a subcommand with its own defaults."""
    parser = argparse.ArgumentParser(prog="rkb import (internal)")
    module.add_arguments(parser)
    namespace = parser.parse_args(argv)
    namespace.verbose = getattr(parent, "verbose", False)
    namespace.config = getattr(parent, "config", None)
    return namespace


def execute(args: argparse.Namespace) -> int:
    """Execute the import command: ingest --resolve, translate, index."""
    directories = args.directories or [Path(DEFAULT_SOURCE).expanduser()]
    dry_run_argv = ["--dry-run"] if args.dry_run else []

    _ensure_api_keys()

    if not os.environ.get("GEMINI_API_KEY") and not args.dry_run:
        print(
            "Error: GEMINI_API_KEY is not set and no local.env was found in the "
            "current directory. Translation cannot run.\n"
            "Fix: run from the kbase repo root, or "
            "`set -a && source local.env && set +a` first."
        )
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        print("Warning: ANTHROPIC_API_KEY is not set; metadata resolution may be degraded.")
        print()

    steps = [
        (
            "Ingest + resolve metadata",
            ingest_cmd,
            [str(directory) for directory in directories] + ["--resolve", *dry_run_argv],
        ),
        ("Translate PDFs to Markdown", translate_cmd, dry_run_argv.copy()),
        ("Index for search", index_cmd, dry_run_argv.copy()),
    ]

    results = []
    overall = 0
    for number, (title, module, argv) in enumerate(steps, 1):
        print(f"{'=' * 70}")
        print(f"Step {number}/{len(steps)}: {title}")
        print(f"{'=' * 70}")
        exit_code = module.execute(_step_namespace(module, argv, args))
        results.append((title, exit_code))
        overall = max(overall, exit_code)
        print()

    print(f"{'=' * 70}")
    print("Import summary")
    print(f"{'=' * 70}")
    for title, exit_code in results:
        status = "ok" if exit_code == 0 else f"FAILED (exit {exit_code})"
        print(f"  {title}: {status}")
    if overall == 0 and not args.dry_run:
        print()
        print("Run `rkb recent` to see the newly imported documents.")

    return overall
