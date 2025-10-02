"""Extract metadata using Gemma2 LLM to combine multiple sources."""

import json
from pathlib import Path

import ollama

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.doi_crossref import DOICrossRefExtractor
from rkb.extractors.metadata.filename_extractor import FilenameExtractor
from rkb.extractors.metadata.first_page_parser import FirstPageParser
from rkb.extractors.metadata.grobid_extractor import GrobidExtractor
from rkb.extractors.metadata.models import DocumentMetadata
from rkb.extractors.metadata.pdf_metadata import PDFMetadataExtractor


class Gemma2Extractor(MetadataExtractor):
    """Extract metadata by combining results from multiple sources using Gemma2 LLM."""

    def __init__(self):
        """Initialize the Gemma2 extractor with all source extractors."""
        self.source_extractors = [
            PDFMetadataExtractor(),
            FilenameExtractor(),
            FirstPageParser(),
            GrobidExtractor(),
            DOICrossRefExtractor(),
        ]
        self.client = ollama.Client(host="http://host.docker.internal:11434")

    @property
    def name(self) -> str:
        return "gemma2"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata by combining results from all sources using Gemma2.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with fields extracted by Gemma2
        """
        # Collect metadata from all sources
        source_metadata = []
        for extractor in self.source_extractors:
            try:
                metadata = extractor.extract(pdf_path)
                source_metadata.append({
                    "source": extractor.name,
                    "doc_type": metadata.doc_type,
                    "title": metadata.title,
                    "authors": metadata.authors,
                    "year": metadata.year,
                    "journal": metadata.journal,
                    "page_count": metadata.page_count,
                })
            except Exception:
                # Skip sources that fail
                continue

        if not source_metadata:
            return DocumentMetadata(extractor=self.name)

        # Build prompt for Gemma2
        prompt = self._build_prompt(source_metadata)

        # Call Gemma2
        try:
            response = self.client.generate(
                model="gemma2:9b-instruct-q4_K_M",
                prompt=prompt,
                stream=False,
                options={
                    "temperature": 0.1,
                }
            )

            # Parse response
            result = self._parse_response(response["response"])
            return DocumentMetadata(
                doc_type=result.get("doc_type"),
                title=result.get("title"),
                authors=result.get("authors"),
                year=result.get("year"),
                journal=result.get("journal"),
                page_count=result.get("page_count"),
                extractor=self.name,
            )

        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _build_prompt(self, source_metadata: list[dict]) -> str:
        """Build prompt for Gemma2 to combine metadata sources.

        Args:
            source_metadata: List of metadata dictionaries from different sources

        Returns:
            Formatted prompt string
        """
        sources_json = json.dumps(source_metadata, indent=2)

        return f"""Our goal is to extract metadata from a PDF document. We have multiple \
sources of metadata, but each may contain errors or be incomplete.

Here are the metadata sources we collected:

{sources_json}

Please analyze these sources and provide the best combined metadata. Return your \
response as a JSON object with the following fields:
- doc_type: Document type (article, inproceedings, report, book, etc.) or null
- title: Document title or null
- authors: List of author names or null
- year: Publication year (integer) or null
- journal: Journal or conference name or null
- page_count: Number of pages (integer) or null

Only include the JSON object in your response, no other text."""

    def _parse_response(self, response_text: str) -> dict:
        """Parse Gemma2 response to extract structured metadata.

        Args:
            response_text: Raw response from Gemma2

        Returns:
            Dictionary with metadata fields
        """
        # Try to find JSON in the response
        # Look for content between { and }
        start = response_text.find("{")
        end = response_text.rfind("}")

        if start == -1 or end == -1:
            return {}

        json_str = response_text[start:end + 1]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}
