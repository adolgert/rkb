"""Tests for Semantic Scholar metadata extractor."""

from unittest.mock import MagicMock, patch

from rkb.extractors.metadata.semantic_scholar import SemanticScholarExtractor


def _mock_response(*, status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@patch("rkb.extractors.metadata.semantic_scholar.requests.get")
def test_extract_by_title_success(mock_get):
    """Successful title search."""
    mock_get.return_value = _mock_response(json_data={
        "data": [{
            "title": "Deep Learning",
            "authors": [{"name": "Y. LeCun"}, {"name": "Y. Bengio"}],
            "year": 2015,
            "abstract": "Deep learning overview.",
            "venue": "Nature",
        }]
    })

    ext = SemanticScholarExtractor()
    meta = ext.extract_by_title("Deep Learning")

    assert meta.title == "Deep Learning"
    assert meta.authors == ["Y. LeCun", "Y. Bengio"]
    assert meta.year == 2015
    assert meta.abstract == "Deep learning overview."
    assert meta.journal == "Nature"


@patch("rkb.extractors.metadata.semantic_scholar.requests.get")
def test_extract_by_title_no_results(mock_get):
    mock_get.return_value = _mock_response(json_data={"data": []})
    ext = SemanticScholarExtractor()
    meta = ext.extract_by_title("nonexistent paper xyz")
    assert meta.title is None


@patch("rkb.extractors.metadata.semantic_scholar.requests.get")
def test_extract_by_doi_success(mock_get):
    """Successful DOI lookup."""
    mock_get.return_value = _mock_response(json_data={
        "title": "A Paper",
        "authors": [{"name": "Smith"}],
        "year": 2020,
        "abstract": "Abstract text.",
        "venue": "ICML",
    })

    ext = SemanticScholarExtractor()
    meta = ext.extract_by_doi("10.1234/test")

    assert meta.title == "A Paper"
    assert meta.year == 2020


@patch("rkb.extractors.metadata.semantic_scholar.requests.get")
def test_extract_by_doi_not_found(mock_get):
    mock_get.return_value = _mock_response(status_code=404)
    ext = SemanticScholarExtractor()
    meta = ext.extract_by_doi("10.9999/missing")
    assert meta.title is None


@patch("rkb.extractors.metadata.semantic_scholar.requests.get")
@patch("rkb.extractors.metadata.semantic_scholar.time.sleep")
def test_retry_on_429(mock_sleep, mock_get):
    """Should retry with backoff on 429 then succeed."""
    mock_get.side_effect = [
        _mock_response(status_code=429),
        _mock_response(json_data={
            "data": [{"title": "Retried", "authors": [], "year": 2023,
                       "abstract": None, "venue": ""}]
        }),
    ]

    ext = SemanticScholarExtractor()
    meta = ext.extract_by_title("Retried")
    assert meta.title == "Retried"
    mock_sleep.assert_called_once()
