"""Extract metadata from PDF XMP/Dublin Core metadata."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

_ARXIV_URL_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})")
_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")
_DOI_RE = re.compile(r"(10\.\d{4,}/[^\s]+)")


@dataclass
class XMPResult:
    """XMP extraction result including identifiers for downstream extractors."""

    metadata: DocumentMetadata
    doi: str | None = None
    arxiv_id: str | None = None


class XMPExtractor(MetadataExtractor):
    """Extract metadata from PDF XMP/Dublin Core streams."""

    @property
    def name(self) -> str:
        return "xmp"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata from XMP. Use extract_with_ids for identifiers."""
        return self.extract_with_ids(pdf_path).metadata

    def extract_with_ids(self, pdf_path: Path) -> XMPResult:
        """Extract metadata and identifiers from PDF XMP."""
        try:
            doc = pymupdf.open(pdf_path)
            xml_str = doc.get_xml_metadata()
            doc.close()

            if not xml_str:
                return XMPResult(metadata=DocumentMetadata(extractor=self.name))

            return self._parse_xmp(xml_str)
        except Exception:
            return XMPResult(metadata=DocumentMetadata(extractor=self.name))

    def _parse_xmp(self, xml_str: str) -> XMPResult:
        """Parse XMP XML and extract Dublin Core fields."""
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return XMPResult(metadata=DocumentMetadata(extractor=self.name))

        ns = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        title = None
        authors = None
        doi = None
        arxiv_id = None

        # Title: dc:title/rdf:Alt/rdf:li
        title_elem = root.find(".//dc:title//rdf:li", ns)
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip() or None

        # Authors: dc:creator/rdf:Seq/rdf:li
        author_elems = root.findall(".//dc:creator//rdf:li", ns)
        if author_elems:
            author_list = [e.text.strip() for e in author_elems if e.text and e.text.strip()]
            authors = author_list or None

        # Identifiers: dc:identifier (may contain DOI or arXiv URL)
        for id_elem in root.findall(".//dc:identifier", ns):
            text = id_elem.text or ""
            if not text:
                # Check rdf:li children
                for li in id_elem.findall(".//rdf:li", ns):
                    if li.text:
                        text = li.text
                        break

            if not text:
                continue

            # Check for arXiv URL/ID
            arxiv_match = _ARXIV_URL_RE.search(text)
            if arxiv_match:
                arxiv_id = arxiv_match.group(1)
                continue

            # Check for DOI
            doi_match = _DOI_RE.search(text)
            if doi_match:
                doi = doi_match.group(1).rstrip(".,;)")
                continue

            # Plain arXiv ID
            arxiv_match = _ARXIV_ID_RE.search(text)
            if arxiv_match and "arxiv" in text.lower():
                arxiv_id = arxiv_match.group(1)

        metadata = DocumentMetadata(
            title=title,
            authors=authors,
            extractor=self.name,
        )

        return XMPResult(metadata=metadata, doi=doi, arxiv_id=arxiv_id)
