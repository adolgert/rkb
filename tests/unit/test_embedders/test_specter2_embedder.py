"""Tests for the SPECTER2 embedder (model is mocked to avoid network downloads)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


def _make_fake_model(dim: int = 768) -> MagicMock:
    """Return a mock SentenceTransformer that produces zero vectors."""
    import numpy as np

    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, **_kw: np.zeros(
        (len(texts), dim), dtype=np.float32
    )
    return mock_model


def _make_specter2(tmpdir: Path, **kwargs: Any):  # noqa: ANN202
    """Helper: instantiate Specter2Embedder with a temp db_path."""
    from rkb.embedders.specter2_embedder import Specter2Embedder

    return Specter2Embedder(db_path=tmpdir / "chroma", **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_embedding_dimension_is_768(tmp_path: Path) -> None:
    """get_embedding_dimension returns 768."""
    embedder = _make_specter2(tmp_path)
    assert embedder.get_embedding_dimension() == 768


def test_embed_returns_nonempty_chunk_count(tmp_path: Path) -> None:
    """embed() stores chunks and reports the correct count."""
    import chromadb

    embedder = _make_specter2(tmp_path)

    mock_model = _make_fake_model()
    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.get_collection.side_effect = chromadb.errors.NotFoundError("not found")
    mock_client.create_collection.return_value = mock_collection

    with (
        patch.object(embedder, "_get_model", return_value=mock_model),
        patch("chromadb.PersistentClient", return_value=mock_client),
    ):
        result = embedder.embed(["Text chunk one.", "Text chunk two."])

    assert result.error_message is None
    assert result.chunk_count == 2
    mock_collection.add.assert_called_once()
    call_kwargs = mock_collection.add.call_args.kwargs
    assert "embeddings" in call_kwargs
    assert len(call_kwargs["embeddings"]) == 2


def test_embed_returns_correct_vector_length(tmp_path: Path) -> None:
    """Stored embedding vectors have length 768."""
    import chromadb

    embedder = _make_specter2(tmp_path)

    captured: dict[str, Any] = {}
    mock_collection = MagicMock()

    def _capture_add(**kwargs: Any) -> None:
        captured.update(kwargs)

    mock_collection.add.side_effect = _capture_add
    mock_client = MagicMock()
    mock_client.get_collection.side_effect = chromadb.errors.NotFoundError("x")
    mock_client.create_collection.return_value = mock_collection

    with (
        patch.object(embedder, "_get_model", return_value=_make_fake_model(768)),
        patch("chromadb.PersistentClient", return_value=mock_client),
    ):
        embedder.embed(["Scientific abstract text."])

    assert len(captured["embeddings"]) == 1
    assert len(captured["embeddings"][0]) == 768


def test_embed_query_returns_vector(tmp_path: Path) -> None:
    """embed_query returns a list of floats of length 768."""
    embedder = _make_specter2(tmp_path)

    with patch.object(embedder, "_get_model", return_value=_make_fake_model()):
        result = embedder.embed_query("stochastic simulation stability")

    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


def test_embed_query_standalone_does_not_need_chroma(tmp_path: Path) -> None:
    """embed_query works without touching Chroma at all."""
    embedder = _make_specter2(tmp_path)

    with patch.object(embedder, "_get_model", return_value=_make_fake_model()):
        result = embedder.embed_query("eigenvalue bounds")

    assert result is not None
    assert len(result) == 768


def test_embed_empty_list_returns_zero_chunks(tmp_path: Path) -> None:
    """Calling embed with an empty list returns a result with chunk_count=0."""
    embedder = _make_specter2(tmp_path)
    result = embedder.embed([])
    assert result.chunk_count == 0
    assert result.error_message is None
