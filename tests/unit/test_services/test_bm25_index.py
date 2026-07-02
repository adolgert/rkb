"""Tests for BM25Index."""

from __future__ import annotations

import pytest

from rkb.services.bm25_index import BM25Index, _tokenise

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------


def test_tokenise_lowercases() -> None:
    assert _tokenise("Hello World") == ["hello", "world"]


def test_tokenise_splits_on_punctuation() -> None:
    tokens = _tokenise("alpha, beta; gamma(delta)")
    assert "alpha" in tokens
    assert "beta" in tokens
    assert "gamma" in tokens
    assert "delta" in tokens


def test_tokenise_preserves_latex_tokens() -> None:
    """Backslash, underscore, and caret must be kept inside tokens."""
    tokens = _tokenise(r"\lambda x_i A^n")
    assert r"\lambda" in tokens
    assert "x_i" in tokens
    assert "a^n" in tokens  # lowercased


# ---------------------------------------------------------------------------
# Build + search
# ---------------------------------------------------------------------------


@pytest.fixture
def tiny_index(tmp_path):  # noqa: ANN001
    """Return a BM25Index with three short chunks."""
    idx = BM25Index(tmp_path / "bm25_dir")
    chunks = [
        ("c1", "stochastic simulation stability convergence"),
        ("c2", "eigenvalue bounds random matrices"),
        ("c3", "Markov chain Monte Carlo methods"),
    ]
    idx.build(chunks)
    return idx


def test_build_and_search_returns_ranked_results(tiny_index: BM25Index) -> None:
    results = tiny_index.search("stochastic simulation")
    assert len(results) > 0
    chunk_ids = [cid for cid, _ in results]
    # c1 should be the top result
    assert chunk_ids[0] == "c1"


def test_normalised_scores_in_unit_interval(tiny_index: BM25Index) -> None:
    results = tiny_index.search("eigenvalue random matrix bounds")
    for _, score in results:
        assert 0.0 <= score <= 1.0


def test_top_result_has_score_one(tiny_index: BM25Index) -> None:
    """The highest-scoring chunk must have a normalised score of 1.0."""
    results = tiny_index.search("Markov chain Monte Carlo")
    assert results[0][1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path) -> None:  # noqa: ANN001
    idx = BM25Index(tmp_path / "bm25_dir")
    chunks = [
        ("doc1_chunk0", "neural network gradient descent"),
        ("doc2_chunk0", "Bayesian inference posterior sampling"),
    ]
    idx.build(chunks)

    # Load into a fresh instance
    idx2 = BM25Index(tmp_path / "bm25_dir")
    loaded = idx2.load()

    assert loaded is True
    results = idx2.search("neural network")
    assert len(results) > 0
    assert results[0][0] == "doc1_chunk0"


# ---------------------------------------------------------------------------
# Missing index
# ---------------------------------------------------------------------------


def test_missing_index_returns_empty_not_error(tmp_path) -> None:  # noqa: ANN001
    idx = BM25Index(tmp_path / "does_not_exist")
    loaded = idx.load()
    assert loaded is False
    results = idx.search("anything")
    assert results == []


def test_is_built_false_before_build(tmp_path) -> None:  # noqa: ANN001
    idx = BM25Index(tmp_path / "bm25_dir")
    assert not idx.is_built()


def test_is_built_true_after_build(tiny_index: BM25Index) -> None:
    assert tiny_index.is_built()
