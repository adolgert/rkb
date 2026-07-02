"""Tests for CrossRef metadata extractor title search."""

from unittest.mock import MagicMock, patch

from rkb.extractors.metadata.doi_crossref import DOICrossRefExtractor


def _mock_response(*, status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _work(title):
    return {
        "title": [title],
        "author": [{"given": "Jane", "family": "Doe"}],
        "published": {"date-parts": [[1998]]},
        "container-title": ["Statistics in Medicine"],
        "type": "journal-article",
    }


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_accepts_strong_match(mock_get):
    """A closely matching returned title is accepted."""
    mock_get.return_value = _mock_response(
        json_data={"message": {"items": [_work("A general relative risk model")]}}
    )
    ext = DOICrossRefExtractor()
    meta = ext.search_by_title("A general relative risk model")
    assert meta.title == "A general relative risk model"
    assert meta.authors == ["Jane Doe"]
    assert meta.year == 1998
    assert meta.extractor == "crossref_title"


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_rejects_near_miss(mock_get):
    """A near-miss title is rejected and empty metadata is returned."""
    mock_get.return_value = _mock_response(
        json_data={
            "message": {"items": [_work("Quasi-Monte Carlo methods in finance")]}
        }
    )
    ext = DOICrossRefExtractor()
    meta = ext.search_by_title("Markov Chain Monte Carlo Methods")
    assert meta.title is None
    assert meta.extractor == "crossref_title"


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_picks_matching_item_among_several(mock_get):
    """The first item that validates is returned, not just the first item."""
    mock_get.return_value = _mock_response(
        json_data={
            "message": {
                "items": [
                    _work("An unrelated survey of clustering"),
                    _work("Bayesian nonparametrics"),
                ]
            }
        }
    )
    ext = DOICrossRefExtractor()
    meta = ext.search_by_title("Bayesian nonparametrics")
    assert meta.title == "Bayesian nonparametrics"


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_429_returns_empty(mock_get):
    """Rate limiting returns empty metadata without raising."""
    mock_get.return_value = _mock_response(status_code=429)
    ext = DOICrossRefExtractor()
    meta = ext.search_by_title("Anything")
    assert meta.title is None
    assert meta.extractor == "crossref_title"


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_503_returns_empty(mock_get):
    """Service unavailable returns empty metadata without raising."""
    mock_get.return_value = _mock_response(status_code=503)
    ext = DOICrossRefExtractor()
    meta = ext.search_by_title("Anything")
    assert meta.title is None


@patch("rkb.extractors.metadata.doi_crossref.requests.get")
def test_search_by_title_uses_polite_user_agent(mock_get):
    """CrossRef polite pool requires a descriptive User-Agent with mailto."""
    mock_get.return_value = _mock_response(json_data={"message": {"items": []}})
    ext = DOICrossRefExtractor()
    ext.search_by_title("Anything")
    headers = mock_get.call_args.kwargs["headers"]
    assert "mailto:claude@dolgert.com" in headers["User-Agent"]
