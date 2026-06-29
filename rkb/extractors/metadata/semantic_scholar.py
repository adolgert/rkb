"""Extract metadata using the Semantic Scholar API."""

import time
from pathlib import Path

import requests

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

_S2_API_BASE = "https://api.semanticscholar.org/graph/v1/paper"
_S2_FIELDS = "title,authors,year,abstract,venue,externalIds"
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 2.0


class SemanticScholarExtractor(MetadataExtractor):
    """Extract metadata from Semantic Scholar API by title or DOI."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["x-api-key"] = api_key

    @property
    def name(self) -> str:
        return "semantic_scholar"

    def extract(self, pdf_path: Path) -> DocumentMetadata:  # noqa: ARG002
        """Not usable without a title or DOI — returns empty metadata."""
        return DocumentMetadata(extractor=self.name)

    def extract_by_title(self, title: str) -> DocumentMetadata:
        """Search Semantic Scholar by title."""
        try:
            response = self._request_with_retry(
                f"{_S2_API_BASE}/search",
                params={"query": title, "fields": _S2_FIELDS, "limit": "1"},
            )
            if response is None:
                return DocumentMetadata(extractor=self.name)

            data = response.json()
            papers = data.get("data", [])
            if not papers:
                return DocumentMetadata(extractor=self.name)
            return self._parse_paper(papers[0])
        except Exception:
            return DocumentMetadata(extractor=self.name)

    def extract_by_doi(self, doi: str) -> DocumentMetadata:
        """Look up a paper by DOI on Semantic Scholar."""
        try:
            response = self._request_with_retry(
                f"{_S2_API_BASE}/DOI:{doi}",
                params={"fields": _S2_FIELDS},
            )
            if response is None:
                return DocumentMetadata(extractor=self.name)

            data = response.json()
            return self._parse_paper(data)
        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _parse_paper(self, paper: dict) -> DocumentMetadata:
        """Convert S2 paper dict to DocumentMetadata."""
        authors = None
        if paper.get("authors"):
            authors = [a["name"] for a in paper["authors"] if a.get("name")]
            if not authors:
                authors = None

        return DocumentMetadata(
            title=paper.get("title"),
            authors=authors,
            year=paper.get("year"),
            abstract=paper.get("abstract"),
            journal=paper.get("venue") or None,
            extractor=self.name,
        )

    def _request_with_retry(
        self, url: str, *, params: dict | None = None
    ) -> requests.Response | None:
        """GET with exponential backoff on 429 responses."""
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES):
            response = requests.get(url, params=params, headers=self._headers, timeout=15)
            if response.status_code == 429:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return None
            if response.status_code != 200:
                return None
            return response
        return None
