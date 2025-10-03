#!/usr/bin/env python3
"""Build metadata database by processing PDFs with Gemma2.

This script recursively scans a directory for PDFs, extracts metadata using
the Gemma2 extractor, and stores results in a JSON database keyed by file hash.
"""

import argparse
import json
import sys
from pathlib import Path

from rkb.core.text_processing import hash_file
from rkb.extractors.metadata.doi_crossref import CrossRefUnavailableError
from rkb.extractors.metadata.gemma2_extractor import Gemma2Extractor, Gemma2UnavailableError


def load_metadata_db(db_path: Path) -> dict:
    """Load metadata database from JSON file.

    Args:
        db_path: Path to JSON database file

    Returns:
        Dictionary mapping file hashes to metadata
    """
    if not db_path.exists():
        return {}

    try:
        with db_path.open("r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_metadata_entry(db_path: Path, file_hash: str, metadata: dict):
    """Save a single metadata entry to the database.

    Args:
        db_path: Path to JSON database file
        file_hash: Hash of the file
        metadata: Metadata dictionary to store
    """
    # Load existing database
    db = load_metadata_db(db_path)

    # Add new entry
    db[file_hash] = metadata

    # Write back to file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with db_path.open("w") as f:
        json.dump(db, f, indent=2)


def metadata_to_dict(metadata) -> dict:
    """Convert DocumentMetadata to dictionary.

    Args:
        metadata: DocumentMetadata object

    Returns:
        Dictionary representation
    """
    return {
        "doc_type": metadata.doc_type,
        "title": metadata.title,
        "authors": metadata.authors,
        "year": metadata.year,
        "journal": metadata.journal,
        "page_count": metadata.page_count,
    }


def find_pdfs(directory: Path) -> list[Path]:
    """Recursively find all PDF files in directory.

    Args:
        directory: Root directory to search

    Returns:
        List of PDF paths
    """
    return sorted(directory.rglob("*.pdf"))


def build_metadata_database(
    input_dir: Path,
    db_path: Path,
    verbose: bool = False,
):
    """Build metadata database from PDFs in directory.

    Args:
        input_dir: Directory to scan for PDFs
        db_path: Path to JSON database file
        verbose: Print progress information
    """
    # Find all PDFs
    pdf_paths = find_pdfs(input_dir)

    if not pdf_paths:
        print(f"No PDFs found in {input_dir}", file=sys.stderr)
        return

    # Load existing database
    db = load_metadata_db(db_path)
    initial_count = len(db)

    if verbose:
        print(f"Found {len(pdf_paths)} PDFs", file=sys.stderr)
        print(f"Database has {initial_count} existing entries", file=sys.stderr)

    # Initialize extractor
    extractor = Gemma2Extractor()

    # Process each PDF
    processed = 0
    skipped = 0

    for i, pdf_path in enumerate(pdf_paths, 1):
        try:
            # Calculate file hash
            file_hash = hash_file(pdf_path)

            # Check if already in database
            if file_hash in db:
                skipped += 1
                if verbose:
                    print(
                        f"[{i}/{len(pdf_paths)}] Skipped (cached): {pdf_path.name}",
                        file=sys.stderr,
                    )
                continue

            # Extract metadata
            if verbose:
                print(f"[{i}/{len(pdf_paths)}] Processing: {pdf_path.name}", file=sys.stderr)

            metadata = extractor.extract(pdf_path)

            # Convert to dict and save
            metadata_dict = metadata_to_dict(metadata)
            save_metadata_entry(db_path, file_hash, metadata_dict)

            processed += 1

            if verbose:
                print(f"  → Saved metadata for hash {file_hash[:12]}...", file=sys.stderr)

        except (CrossRefUnavailableError, Gemma2UnavailableError) as e:
            error_source = (
                "CrossRef API" if isinstance(e, CrossRefUnavailableError) else "Gemma2/Ollama"
            )
            print(
                f"\n⛔ {error_source} Error: {e}",
                file=sys.stderr,
            )
            print(
                f"  Processed {processed} files before stopping.",
                file=sys.stderr,
            )
            print(
                "  The database has been saved with current progress.",
                file=sys.stderr,
            )
            print(
                "  Please wait and restart later to continue.",
                file=sys.stderr,
            )
            break

        except Exception as e:
            print(f"[{i}/{len(pdf_paths)}] Error processing {pdf_path}: {e}", file=sys.stderr)
            continue

    # Print summary
    final_count = len(load_metadata_db(db_path))
    if verbose:
        print("\nSummary:", file=sys.stderr)
        print(f"  PDFs found: {len(pdf_paths)}", file=sys.stderr)
        print(f"  Processed: {processed}", file=sys.stderr)
        print(f"  Skipped (cached): {skipped}", file=sys.stderr)
        print(f"  Database entries: {initial_count} → {final_count}", file=sys.stderr)


def main():
    """Main entry point for metadata database builder."""
    parser = argparse.ArgumentParser(
        description="Build metadata database from PDFs using Gemma2"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory to scan for PDFs",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/metadata_db.json"),
        help="Path to JSON database file (default: data/metadata_db.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print progress information",
    )

    args = parser.parse_args()

    # Validate input directory
    if not args.input_dir.exists():
        print(f"Error: Directory not found: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.input_dir.is_dir():
        print(f"Error: Not a directory: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    # Build database
    build_metadata_database(
        input_dir=args.input_dir.resolve(),
        db_path=args.db,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
