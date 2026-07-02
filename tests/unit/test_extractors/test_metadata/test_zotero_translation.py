"""Tests for the Zotero translation-server metadata extractor."""

from unittest.mock import MagicMock, patch

import requests

from rkb.extractors.metadata.zotero_translation import ZoteroTranslationExtractor


def _mock_response(*, status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    return resp


_JOURNAL_ITEM = {
    "itemType": "journalArticle",
    "title": "Integrated lithium niobate photonic millimetre-wave radar",
    "creators": [
        {"firstName": "Sha", "lastName": "Zhu", "creatorType": "author"},
        {"firstName": "Yiwen", "lastName": "Zhang", "creatorType": "author"},
        {"name": "Photonics Consortium", "creatorType": "author"},
        {"firstName": "An", "lastName": "Editor", "creatorType": "editor"},
    ],
    "publicationTitle": "Nature Photonics",
    "date": "02/2025",
    "DOI": "10.1038/s41566-024-01608-7",
    "abstractNote": "",
}

_PREPRINT_ITEM = {
    "itemType": "preprint",
    "title": "High Accuracy and High Fidelity Extraction of Neural Networks",
    "creators": [
        {"firstName": "Matthew", "lastName": "Jagielski", "creatorType": "author"},
    ],
    "repository": "arXiv",
    "date": "2020-03-03",
    "abstractNote": "In a model extraction attack...",
}


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_journal_article_mapping(mock_post):
    mock_post.return_value = _mock_response(json_data=[_JOURNAL_ITEM])

    meta = ZoteroTranslationExtractor().extract_by_identifier("10.1038/s41566-024-01608-7")

    assert meta.extractor == "zotero_translation"
    assert meta.title == "Integrated lithium niobate photonic millimetre-wave radar"
    # Editors excluded; single-field institutional names kept.
    assert meta.authors == ["Sha Zhu", "Yiwen Zhang", "Photonics Consortium"]
    assert meta.year == 2025
    assert meta.journal == "Nature Photonics"
    assert meta.doc_type == "journal-article"
    assert meta.abstract is None  # empty string normalized to None


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_preprint_mapping(mock_post):
    mock_post.return_value = _mock_response(json_data=[_PREPRINT_ITEM])

    meta = ZoteroTranslationExtractor().extract_by_identifier("arXiv:1909.01838")

    assert meta.doc_type == "preprint"
    assert meta.year == 2020
    assert meta.journal == "arXiv"
    assert meta.abstract == "In a model extraction attack..."


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_identifier_sent_as_plain_text(mock_post):
    mock_post.return_value = _mock_response(json_data=[_JOURNAL_ITEM])

    ZoteroTranslationExtractor(server_url="http://example:1969/").extract_by_identifier(
        "10.1000/xyz"
    )

    args, kwargs = mock_post.call_args
    assert args[0] == "http://example:1969/search"
    assert kwargs["data"] == b"10.1000/xyz"
    assert kwargs["headers"]["Content-Type"] == "text/plain"


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_unknown_identifier_returns_empty(mock_post):
    mock_post.return_value = _mock_response(status_code=501)

    meta = ZoteroTranslationExtractor().extract_by_identifier("10.9999/nope")

    assert meta.title is None
    assert meta.extractor == "zotero_translation"


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_server_down_returns_empty(mock_post):
    mock_post.side_effect = requests.ConnectionError("refused")

    meta = ZoteroTranslationExtractor().extract_by_identifier("10.1000/xyz")

    assert meta.title is None


@patch("rkb.extractors.metadata.zotero_translation.requests.post")
def test_empty_result_list_returns_empty(mock_post):
    mock_post.return_value = _mock_response(json_data=[])

    meta = ZoteroTranslationExtractor().extract_by_identifier("10.1000/xyz")

    assert meta.title is None


def test_server_url_from_environment(monkeypatch):
    monkeypatch.setenv("TRANSLATION_SERVER_URL", "http://otherhost:1969")
    ext = ZoteroTranslationExtractor()
    assert ext._server_url == "http://otherhost:1969"
