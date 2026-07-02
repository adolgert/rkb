"""Tests for the Gemini Flash last-resort metadata extractor.

All tests mock the google-genai client: no network calls and no real API key.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from rkb.extractors.metadata.gemini_flash import GeminiFlashExtractor

_TITLE_PAGE = (
    "# Some OCR Heading\n\n"
    "A Study of Reversible Markov Chains\n\n"
    "by Jane Q. Researcher and John Doe\n\n"
    "Journal of Applied Probability, 1987\n\n"
    "Abstract: we study things."
)


def _fake_client(payload: dict) -> MagicMock:
    """Build a mock google-genai client whose response.text is JSON payload."""
    response = MagicMock()
    response.text = json.dumps(payload)
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch):
    """Never inherit a real key from the environment during tests."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL_NAME", raising=False)


def test_construction_without_key_succeeds():
    ext = GeminiFlashExtractor()
    assert ext.name == "gemini_flash"
    assert ext._client is None


def test_missing_key_returns_empty_without_constructing_client():
    ext = GeminiFlashExtractor()
    with patch("google.genai.Client") as mock_client_cls:
        meta = ext.extract_from_text(_TITLE_PAGE)
    assert meta.title is None
    assert meta.extractor == "gemini_flash"
    mock_client_cls.assert_not_called()


def test_happy_path_maps_fields():
    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client(
        {
            "title": "A Study of Reversible Markov Chains",
            "authors": ["Jane Q. Researcher", "John Doe"],
            "year": 1987,
            "journal": "Journal of Applied Probability",
        }
    )
    with patch("google.genai.Client", return_value=client) as mock_client_cls:
        meta = ext.extract_from_text(_TITLE_PAGE)

    assert meta.title == "A Study of Reversible Markov Chains"
    assert meta.authors == ["Jane Q. Researcher", "John Doe"]
    assert meta.year == 1987
    assert meta.journal == "Journal of Applied Probability"
    assert meta.extractor == "gemini_flash"
    mock_client_cls.assert_called_once_with(api_key="test-key")


def test_hallucinated_title_rejected():
    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client(
        {
            "title": "A Completely Different Fabricated Title",
            "authors": ["Ghost Author"],
            "year": 2001,
            "journal": None,
        }
    )
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text(_TITLE_PAGE)

    assert meta.title is None
    assert meta.authors is None


def test_title_split_across_ocr_line_breaks_accepted():
    text = "A Study of\nReversible\nMarkov Chains\n\nby Jane Q. Researcher"
    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client(
        {
            "title": "A Study of Reversible Markov Chains",
            "authors": ["Jane Q. Researcher"],
            "year": None,
            "journal": None,
        }
    )
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text(text)

    assert meta.title == "A Study of Reversible Markov Chains"


def test_very_short_title_rejected():
    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client({"title": "AB", "authors": [], "year": None, "journal": None})
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text("AB appears here but is too short")
    assert meta.title is None


def test_api_exception_returns_empty():
    ext = GeminiFlashExtractor(api_key="test-key")
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("boom")
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text(_TITLE_PAGE)
    assert meta.title is None
    assert meta.extractor == "gemini_flash"


def test_malformed_json_returns_empty():
    ext = GeminiFlashExtractor(api_key="test-key")
    response = MagicMock()
    response.text = "not valid json"
    client = MagicMock()
    client.models.generate_content.return_value = response
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text(_TITLE_PAGE)
    assert meta.title is None


def test_non_int_year_and_bad_authors_dropped():
    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client(
        {
            "title": "A Study of Reversible Markov Chains",
            "authors": "not a list",
            "year": "nineteen eighty seven",
            "journal": "",
        }
    )
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract_from_text(_TITLE_PAGE)
    assert meta.title == "A Study of Reversible Markov Chains"
    assert meta.authors is None
    assert meta.year is None
    assert meta.journal is None


def test_extract_reads_markdown_beside_pdf(tmp_path):
    hash_dir = tmp_path / "sha256" / "aa" / "aa" / ("a" * 64)
    extraction_dir = hash_dir / "extractions" / "marker-pdf-1.10.2"
    extraction_dir.mkdir(parents=True)
    (extraction_dir / "extracted.md").write_text(_TITLE_PAGE)
    pdf_path = hash_dir / "scan.pdf"
    pdf_path.write_bytes(b"pdf")

    ext = GeminiFlashExtractor(api_key="test-key")
    client = _fake_client(
        {
            "title": "A Study of Reversible Markov Chains",
            "authors": ["Jane Q. Researcher"],
            "year": 1987,
            "journal": None,
        }
    )
    with patch("google.genai.Client", return_value=client):
        meta = ext.extract(pdf_path)
    assert meta.title == "A Study of Reversible Markov Chains"


def test_extract_missing_markdown_returns_empty(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"pdf")
    ext = GeminiFlashExtractor(api_key="test-key")
    meta = ext.extract(pdf_path)
    assert meta.title is None
    assert meta.extractor == "gemini_flash"
