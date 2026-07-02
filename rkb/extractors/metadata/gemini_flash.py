"""Last-resort metadata extractor that reads a document's text with Gemini Flash.

Pre-DOI scans often have no resolvable identifiers, and their marker-pdf OCR
Markdown carries headings that are not the title, so every registrar-based
extractor returns nothing. An LLM reading the first page can transcribe the
title, authors, year, and journal the way a human would. This extractor is the
final fallback in the resolver chain and, because an LLM can invent text, it
accepts a result only when the returned title actually appears in the supplied
document text (see ``_title_in_text``).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Only the opening of the document is needed to identify a paper; capping the
# prompt keeps token cost bounded and well inside the model's context window.
_MAX_INPUT_CHARS = 8000

# Shorter strings are almost never real titles and defeat the containment guard.
_MIN_TITLE_CHARS = 4

_DEFAULT_MODEL = "gemini-2.5-flash"

_PROMPT = (
    "You are transcribing bibliographic metadata from the first page of an "
    "academic document. Return the title, authors, publication year, and "
    "journal or venue EXACTLY as printed in the text below. Transcribe only "
    "what actually appears in the text; never guess, infer, or invent. Use "
    "null for any field that is not present. Reconstruct the title exactly as "
    "printed, joining any line breaks into a single line. Authors must be a "
    "list of full-name strings.\n\nDOCUMENT TEXT:\n"
)


def _normalize(text: str) -> str:
    """Casefold text and reduce punctuation and whitespace to single spaces.

    Collapsing all whitespace lets a title that OCR split across several lines
    still be found verbatim in the document text.
    """
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


class GeminiFlashExtractor(MetadataExtractor):
    """Transcribe metadata from document text with Gemini Flash (last resort)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Store configuration only; the API client is created lazily.

        Construction never touches the network or requires a key, so the
        resolver can always instantiate this extractor. When no key is
        available, ``extract_from_text`` returns empty metadata.
        """
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("GEMINI_MODEL_NAME") or _DEFAULT_MODEL
        self._client = None

    @property
    def name(self) -> str:
        return "gemini_flash"

    def _get_client(self):
        """Create and cache the google-genai client on first use."""
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def extract_from_text(self, text: str) -> DocumentMetadata:
        """Ask Gemini to transcribe metadata from ``text``; guard against hallucination.

        Returns empty metadata when no key is configured, on any API/parse
        error, or when the returned title does not appear in ``text``. No
        retries: a later enrich run retries the whole resolution.
        """
        empty = DocumentMetadata(extractor=self.name)
        if not self._api_key or not text:
            return empty

        try:
            from google.genai import types

            schema = types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING, nullable=True),
                    "authors": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "year": types.Schema(type=types.Type.INTEGER, nullable=True),
                    "journal": types.Schema(type=types.Type.STRING, nullable=True),
                },
            )
            config = types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            )
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=_PROMPT + text[:_MAX_INPUT_CHARS],
                config=config,
            )
            data = json.loads(response.text)
        except Exception:
            logger.debug("Gemini Flash extraction failed", exc_info=True)
            return empty

        return self._build_metadata(data, text)

    def _build_metadata(self, data: dict, text: str) -> DocumentMetadata:
        """Validate the parsed LLM response and turn it into DocumentMetadata."""
        empty = DocumentMetadata(extractor=self.name)
        if not isinstance(data, dict):
            return empty

        title = data.get("title")
        if not isinstance(title, str):
            return empty
        title = title.strip()
        if len(title) < _MIN_TITLE_CHARS or not self._title_in_text(title, text):
            return empty

        authors = data.get("authors")
        if isinstance(authors, list):
            authors = [a.strip() for a in authors if isinstance(a, str) and a.strip()]
            authors = authors or None
        else:
            authors = None

        year = data.get("year")
        year = year if isinstance(year, int) else None

        journal = data.get("journal")
        journal = journal.strip() if isinstance(journal, str) and journal.strip() else None

        return DocumentMetadata(
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            extractor=self.name,
        )

    @staticmethod
    def _title_in_text(title: str, text: str) -> bool:
        """Return True if the normalized title appears verbatim in the text.

        This is the anti-hallucination guard: the LLM may fabricate a
        plausible-looking title, so a title is trusted only when it survives
        whitespace/case/punctuation normalization and is contained in the
        (identically normalized) source text.
        """
        norm_title = _normalize(title)
        if not norm_title:
            return False
        return norm_title in _normalize(text)

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Read the marker-pdf Markdown beside the PDF and delegate to extract_from_text.

        The Markdown is located with a small local glob rather than importing
        ``rkb.collection`` (which this layer may not depend on). Missing
        Markdown yields empty metadata.
        """
        text = self._read_markdown(pdf_path)
        if text is None:
            return DocumentMetadata(extractor=self.name)
        return self.extract_from_text(text)

    @staticmethod
    def _read_markdown(pdf_path: Path) -> str | None:
        """Return the newest marker-pdf (or nougat) extraction text, if any."""
        extractions = pdf_path.parent / "extractions"
        for pattern, name in (("marker-pdf-*", "extracted.md"), ("nougat-ocr-*", "extracted.mmd")):
            candidates = sorted(extractions.glob(f"{pattern}/{name}"), reverse=True)
            if candidates:
                try:
                    return candidates[0].read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    return None
        return None
