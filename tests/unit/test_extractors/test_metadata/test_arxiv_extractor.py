"""Tests for arXiv metadata extractor."""

import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rkb.extractors.metadata.arxiv_extractor import ArxivExtractor


def test_id_from_filename_standard():
    assert ArxivExtractor.id_from_filename("2301.12345.pdf") == "2301.12345"


def test_id_from_filename_with_prefix():
    assert ArxivExtractor.id_from_filename("paper_2301.12345v2.pdf") == "2301.12345"


def test_id_from_filename_no_match():
    assert ArxivExtractor.id_from_filename("my_paper.pdf") is None


@pytest.fixture()
def _mock_arxiv_module():
    """Inject a fake `arxiv` module into sys.modules."""
    mock_mod = MagicMock()
    original = sys.modules.get("arxiv")
    sys.modules["arxiv"] = mock_mod
    yield mock_mod
    if original is None:
        sys.modules.pop("arxiv", None)
    else:
        sys.modules["arxiv"] = original


def test_extract_by_id_success(_mock_arxiv_module):
    """Successful arXiv API lookup."""
    mock_arxiv = _mock_arxiv_module
    paper = SimpleNamespace(
        title="Test Paper",
        authors=[SimpleNamespace(name="A. Author"), SimpleNamespace(name="B. Writer")],
        published=datetime(2023, 1, 15),
        summary="This is the abstract.",
        categories=["cs.AI", "cs.LG"],
    )
    mock_client = MagicMock()
    mock_client.results.return_value = [paper]
    mock_arxiv.Client.return_value = mock_client
    mock_arxiv.Search.return_value = "search_obj"

    ext = ArxivExtractor()
    meta = ext.extract_by_id("2301.12345")

    assert meta.title == "Test Paper"
    assert meta.authors == ["A. Author", "B. Writer"]
    assert meta.year == 2023
    assert meta.abstract == "This is the abstract."
    assert meta.extractor == "arxiv"


def test_extract_by_id_no_results(_mock_arxiv_module):
    """arXiv returns no results."""
    mock_arxiv = _mock_arxiv_module
    mock_client = MagicMock()
    mock_client.results.return_value = []
    mock_arxiv.Client.return_value = mock_client
    mock_arxiv.Search.return_value = "search_obj"

    ext = ArxivExtractor()
    meta = ext.extract_by_id("9999.99999")

    assert meta.title is None
    assert meta.extractor == "arxiv"


def test_extract_by_id_exception(_mock_arxiv_module):
    """arXiv API raises exception — returns empty metadata."""
    mock_arxiv = _mock_arxiv_module
    mock_arxiv.Client.side_effect = Exception("network error")

    ext = ArxivExtractor()
    meta = ext.extract_by_id("2301.12345")

    assert meta.title is None
