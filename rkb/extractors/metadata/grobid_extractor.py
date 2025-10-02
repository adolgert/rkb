"""Extract metadata using GROBID service."""

import contextlib
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata


class GrobidExtractor(MetadataExtractor):
    """Extract metadata using GROBID service."""

    def __init__(self, grobid_url: str = "http://172.17.0.1:8070"):
        """Initialize GROBID extractor.

        Args:
            grobid_url: Base URL for GROBID service
        """
        self.grobid_url = grobid_url
        self.api_endpoint = f"{grobid_url}/api/processHeaderDocument"

    @property
    def name(self) -> str:
        return "grobid"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata using GROBID.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with fields extracted by GROBID
        """
        try:
            with pdf_path.open("rb") as f:
                files = {"input": f}
                headers = {"Accept": "application/xml"}
                response = requests.post(
                    self.api_endpoint, files=files, headers=headers, timeout=30
                )

            if response.status_code != 200:
                return DocumentMetadata(extractor=self.name)

            # Parse XML response
            xml_content = response.text
            return self._parse_grobid_xml(xml_content)

        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _parse_grobid_xml(self, xml_content: str) -> DocumentMetadata:
        """Parse GROBID XML response.

        Args:
            xml_content: XML string from GROBID

        Returns:
            DocumentMetadata with extracted fields
        """
        try:
            root = ET.fromstring(xml_content)

            # Define namespace
            ns = {"tei": "http://www.tei-c.org/ns/1.0"}

            # Extract title
            title_elem = root.find(".//tei:titleStmt/tei:title", ns)
            title = title_elem.text if title_elem is not None and title_elem.text else None

            # Extract authors
            authors = []
            for author in root.findall(".//tei:sourceDesc//tei:author", ns):
                # Try to get forename and surname
                forename = author.find(".//tei:forename", ns)
                surname = author.find(".//tei:surname", ns)

                if surname is not None and surname.text:
                    name_parts = []
                    if forename is not None and forename.text:
                        name_parts.append(forename.text)
                    name_parts.append(surname.text)
                    authors.append(" ".join(name_parts))

            # Extract year
            year = None
            date_elem = root.find(".//tei:publicationStmt//tei:date", ns)
            if date_elem is not None:
                year_str = date_elem.get("when", "")
                if year_str and len(year_str) >= 4:
                    with contextlib.suppress(ValueError):
                        year = int(year_str[:4])

            # Extract journal/venue
            journal = None
            # Try journal title
            journal_elem = root.find(".//tei:monogr/tei:title[@level='j']", ns)
            if journal_elem is not None and journal_elem.text:
                journal = journal_elem.text
            else:
                # Try meeting/conference
                meeting_elem = root.find(".//tei:monogr/tei:meeting", ns)
                if meeting_elem is not None and meeting_elem.text:
                    journal = meeting_elem.text

            # Extract document type (GROBID doesn't always provide this)
            doc_type = None

            return DocumentMetadata(
                doc_type=doc_type,
                title=title,
                authors=authors if authors else None,
                year=year,
                journal=journal,
                page_count=None,
                extractor=self.name,
            )

        except Exception:
            return DocumentMetadata(extractor=self.name)
