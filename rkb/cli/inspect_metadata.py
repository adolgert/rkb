#!/usr/bin/env python3
"""Inspection script to review metadata extraction results.

This script walks a directory tree to find PDFs, runs all metadata extractors,
and displays results for human review.
"""

import argparse
import sys
from pathlib import Path

from rkb.extractors.metadata.doi_crossref import DOICrossRefExtractor
from rkb.extractors.metadata.filename_extractor import FilenameExtractor
from rkb.extractors.metadata.first_page_parser import FirstPageParser
from rkb.extractors.metadata.gemma2_extractor import Gemma2Extractor
from rkb.extractors.metadata.grobid_extractor import GrobidExtractor
from rkb.extractors.metadata.pdf_metadata import PDFMetadataExtractor


def find_recent_pdfs(directory: Path, limit: int = 30) -> list[Path]:
    """Find most recent PDF files in directory tree.

    Args:
        directory: Root directory to search
        limit: Maximum number of PDFs to return

    Returns:
        List of PDF paths sorted by modification time (most recent first)
    """
    pdfs = [pdf_path for pdf_path in directory.rglob("*.pdf") if pdf_path.is_file()]

    # Sort by modification time, most recent first
    pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return pdfs[:limit]


def inspect_metadata(pdf_paths: list[Path], output_file: Path | None = None):
    """Run all extractors on PDFs and display results.

    Args:
        pdf_paths: List of PDF paths to process
        output_file: Optional file to write output to (default: stdout)
    """
    # Initialize all extractors
    extractors = [
        PDFMetadataExtractor(),
        FilenameExtractor(),
        FirstPageParser(),
        GrobidExtractor(),
        DOICrossRefExtractor(),
        Gemma2Extractor(),
    ]

    # Open output stream
    output = open(output_file, "w") if output_file else sys.stdout

    try:
        for _i, pdf_path in enumerate(pdf_paths, 1):
            # Print progress to stderr

            # Print file URL
            file_url = pdf_path.as_uri()
            output.write(f"\n{file_url}\n\n")

            # Run each extractor
            for extractor in extractors:
                try:
                    metadata = extractor.extract(pdf_path)

                    # Format output
                    line1 = metadata.format_line1()
                    line2 = metadata.format_line2()

                    output.write(f"[{extractor.name}]\t{line1}\n")
                    output.write(f"\t\t{line2}\n\n")

                except Exception as e:
                    output.write(f"[{extractor.name}]\tERROR: {e!s}\n\n")

            output.flush()

    finally:
        if output_file:
            output.close()


def main():
    """Main entry point for inspection script."""
    parser = argparse.ArgumentParser(description="Inspect metadata extraction from academic PDFs")
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Number of documents to process (default: 30)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path.home() / "Zotero" / "storage",
        help="Directory to scan (default: ~/Zotero/storage)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Validate directory
    if not args.dir.exists():
        sys.exit(1)

    if not args.dir.is_dir():
        sys.exit(1)

    # Find PDFs
    pdf_paths = find_recent_pdfs(args.dir.resolve(), args.limit)

    if not pdf_paths:
        sys.exit(1)

    # Process PDFs
    inspect_metadata(pdf_paths, args.output)


if __name__ == "__main__":
    main()
