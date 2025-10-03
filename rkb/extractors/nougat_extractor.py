"""Nougat-based PDF extractor with chunked processing for robust extraction."""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from rkb.core.interfaces import ExtractorInterface
from rkb.core.models import ExtractionResult, ExtractionStatus
from rkb.core.text_processing import (
    chunk_text_by_pages,
    clean_extracted_text,
    create_chunk_metadata,
    extract_arxiv_id,
    extract_doi,
    hash_file,
)
from rkb.extractors.base import register_extractor


class NougatExtractor(ExtractorInterface):
    """Nougat OCR extractor with chunked processing for robust extraction."""

    def __init__(
        self,
        chunk_size: int = 1,
        max_pages: int = 50,
        timeout_per_chunk: int = 120,
        min_content_length: int = 50,
        output_dir: Path | None = None,
    ):
        """Initialize Nougat extractor.

        Args:
            chunk_size: Number of pages to process per chunk
            max_pages: Maximum number of pages to process
            timeout_per_chunk: Timeout in seconds per chunk
            min_content_length: Minimum content length to consider successful
            output_dir: Directory for extraction output
        """
        self.chunk_size = chunk_size
        self.max_pages = max_pages
        self.timeout_per_chunk = timeout_per_chunk
        self.min_content_length = min_content_length
        self.output_dir = output_dir or Path("rkb_extractions")

    @property
    def name(self) -> str:
        """Return the extractor name."""
        return "nougat"

    @property
    def version(self) -> str:
        """Return the extractor version."""
        return "1.0.0"

    def extract(self, source_path: Path, doc_id: str | None = None) -> ExtractionResult:
        """Extract text from PDF using chunked Nougat processing.

        Args:
            source_path: Path to the PDF file
            doc_id: Document ID for consistent output naming

        Returns:
            ExtractionResult with extracted content and metadata
        """
        source_path = Path(source_path)
        if not source_path.exists():
            return ExtractionResult(
                doc_id=doc_id or str(source_path),
                status=ExtractionStatus.FAILED,
                error_message=f"File not found: {source_path}",
            )

        # Use provided doc_id or generate one
        if not doc_id:
            from uuid import uuid4

            doc_id = str(uuid4())

        extraction_id = f"{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            # Get actual page count from PDF using PyMuPDF
            import fitz

            try:
                pdf_doc = fitz.open(source_path)
                actual_page_count = len(pdf_doc)
                pdf_doc.close()
            except Exception:
                actual_page_count = None

            # Calculate file hash for deduplication
            _ = hash_file(source_path)

            # Extract metadata from filename and content
            _ = extract_arxiv_id(source_path.name)

            # Process PDF in chunks
            chunks_result = self._extract_pdf_chunks(source_path, extraction_id, actual_page_count)

            if not chunks_result["content"]:
                return ExtractionResult(
                    doc_id=doc_id,
                    extraction_id=extraction_id,
                    status=ExtractionStatus.FAILED,
                    error_message="No content extracted from any chunks",
                )

            # Clean and process the extracted text
            cleaned_content = clean_extracted_text(chunks_result["content"])

            # Extract DOI from content
            _ = extract_doi(cleaned_content)

            # Chunk the text for embedding with page tracking
            text_chunks_with_pages = chunk_text_by_pages(cleaned_content)
            chunk_metadata = create_chunk_metadata(text_chunks_with_pages)

            # Extract just text for backward compatibility
            text_chunks = [chunk for chunk, _ in text_chunks_with_pages]

            # Use PathResolver for consistent output location
            from rkb.core.paths import PathResolver

            extraction_path = PathResolver.get_extraction_path(doc_id, self.output_dir)

            # Ensure directory exists
            PathResolver.ensure_extraction_dir(doc_id, self.output_dir)

            # Save extraction to file
            extraction_path.write_text(cleaned_content, encoding="utf-8")

            return ExtractionResult(
                doc_id=doc_id,
                extraction_id=extraction_id,
                status=ExtractionStatus.COMPLETE,
                extraction_path=extraction_path,
                content=cleaned_content,
                chunks=text_chunks,
                chunk_metadata=chunk_metadata,
                page_count=chunks_result["total_pages_processed"],
                extractor_name=self.name,
                extractor_version=self.version,
            )

        except Exception as e:
            return ExtractionResult(
                doc_id=doc_id,
                extraction_id=extraction_id,
                status=ExtractionStatus.FAILED,
                error_message=str(e),
            )

    def _extract_pdf_chunks(
        self, pdf_path: Path, extraction_id: str, actual_page_count: int | None = None
    ) -> dict:
        """Extract PDF using small chunks to bypass problematic pages.

        Args:
            pdf_path: Path to the PDF file
            extraction_id: Unique extraction identifier

        Returns:
            Dictionary with extraction results
        """
        successful_chunks = []
        failed_chunks = []
        total_content = []

        # Create temporary directory for chunk processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Process in small chunks
            for start_page in range(1, self.max_pages + 1, self.chunk_size):
                end_page = min(start_page + self.chunk_size - 1, self.max_pages)

                try:
                    chunk_content = self._extract_chunk(pdf_path, start_page, end_page, temp_path)

                    if chunk_content and len(chunk_content) > self.min_content_length:
                        # Add page delimiter
                        total_content.append(f"\n\n<!-- Pages {start_page}-{end_page} -->\n\n")
                        total_content.append(chunk_content)
                        successful_chunks.append((start_page, end_page))
                    else:
                        failed_chunks.append(
                            (start_page, end_page, "Empty or insufficient content")
                        )

                except subprocess.TimeoutExpired:
                    failed_chunks.append((start_page, end_page, "Timeout"))
                except Exception as e:
                    failed_chunks.append((start_page, end_page, str(e)))

        # Combine content with metadata header
        if total_content:
            header = self._create_extraction_header(
                pdf_path, extraction_id, successful_chunks, failed_chunks, actual_page_count
            )
            combined_content = header + "\n".join(total_content)
        else:
            combined_content = ""

        return {
            "content": combined_content,
            "successful_chunks": successful_chunks,
            "failed_chunks": failed_chunks,
            "total_pages_processed": len(successful_chunks) * self.chunk_size,
        }

    def _extract_chunk(self, pdf_path: Path, start_page: int, end_page: int, temp_dir: Path) -> str:
        """Extract a single chunk of pages.

        Args:
            pdf_path: Path to the PDF file
            start_page: Starting page number
            end_page: Ending page number
            temp_dir: Temporary directory for processing

        Returns:
            Extracted content from the chunk

        Raises:
            subprocess.TimeoutExpired: If extraction times out
            Exception: If extraction fails
        """
        cmd = [
            "nougat",
            str(pdf_path),
            "--out",
            str(temp_dir),
            "--pages",
            f"{start_page}-{end_page}",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_per_chunk,
            check=False,
        )

        # Check for output file
        expected_output = temp_dir / f"{pdf_path.stem}.mmd"

        if result.returncode == 0 and expected_output.exists():
            content = expected_output.read_text(encoding="utf-8").strip()
            expected_output.unlink()  # Clean up immediately
            return content
        # Analyze error for better reporting
        error_info = self._analyze_chunk_error(result.stderr, start_page, end_page)
        raise RuntimeError(error_info)

    def _analyze_chunk_error(self, stderr: str, start_page: int, end_page: int) -> str:
        """Analyze stderr to identify specific error types.

        Args:
            stderr: Error output from nougat
            start_page: Starting page number
            end_page: Ending page number

        Returns:
            Human-readable error description
        """
        if not stderr:
            return f"No error output (pages {start_page}-{end_page})"

        error_patterns = {
            "Failed to load page": "Corrupted page",
            "list index out of range": "Dataloader error",
            "Image not found": "Missing images",
            "repetitions": "Repetitive content",
            "degrees of freedom": "Statistical error",
        }

        for pattern, description in error_patterns.items():
            if pattern in stderr:
                return f"{description} (pages {start_page}-{end_page})"

        return f"Unknown error (pages {start_page}-{end_page})"

    def _create_extraction_header(
        self,
        pdf_path: Path,
        extraction_id: str,
        successful_chunks: list,
        failed_chunks: list,
        actual_page_count: int | None = None,
    ) -> str:
        """Create metadata header for extracted content.

        Args:
            pdf_path: Path to the original PDF
            extraction_id: Unique extraction identifier
            successful_chunks: List of successfully processed chunks
            failed_chunks: List of failed chunks
            actual_page_count: Actual page count from PyMuPDF

        Returns:
            Formatted header string
        """
        page_info = (
            f"<!-- Actual page count: {actual_page_count} -->\n" if actual_page_count else ""
        )
        return f"""<!-- Nougat extraction of {pdf_path.name} -->
<!-- Extraction ID: {extraction_id} -->
{page_info}<!-- Successful chunks: {len(successful_chunks)} -->
<!-- Failed chunks: {len(failed_chunks)} -->
<!-- Extraction date: {datetime.now().isoformat()} -->

"""

    def get_capabilities(self) -> dict:
        """Get extractor capabilities and configuration.

        Returns:
            Dictionary describing extractor capabilities
        """
        return {
            "name": "nougat",
            "description": "Nougat OCR with chunked processing for robust extraction",
            "supported_formats": [".pdf"],
            "features": [
                "mathematical_content",
                "equation_extraction",
                "chunked_processing",
                "error_recovery",
            ],
            "configuration": {
                "chunk_size": self.chunk_size,
                "max_pages": self.max_pages,
                "timeout_per_chunk": self.timeout_per_chunk,
                "min_content_length": self.min_content_length,
            },
        }


# Register the extractor
register_extractor("nougat", NougatExtractor)
