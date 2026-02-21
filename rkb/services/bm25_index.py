"""BM25 keyword index for hybrid search."""

from __future__ import annotations

import json
import logging
import pickle
import re
from pathlib import Path

LOGGER = logging.getLogger("rkb.services.bm25_index")

# Tokenisation: split on whitespace and selected punctuation, but keep
# LaTeX structure tokens (backslash, underscore, caret) so that
# \lambda, x_i, etc. are matched by keyword queries.
_SPLIT_RE = re.compile(r"[\s,;:()\[\]{}'\"]+")


def _tokenise(text: str) -> list[str]:
    """Tokenise text for BM25 indexing.

    Lowercases, splits on whitespace and common punctuation, but preserves
    LaTeX tokens such as ``\\lambda``, ``x_i``, and ``A^n``.

    Args:
        text: Raw text string.

    Returns:
        List of lowercase tokens (empty strings filtered out).
    """
    tokens = _SPLIT_RE.split(text.lower())
    return [t for t in tokens if t]


class BM25Index:
    """Persistent BM25 index over document chunks.

    Attributes:
        index_path: Directory where the index files are stored.
    """

    _INDEX_FILE = "bm25_index.pkl"
    _CHUNKS_FILE = "bm25_chunks.json"

    def __init__(self, index_path: Path) -> None:
        """Initialise (but do not load) the BM25 index.

        Args:
            index_path: Directory for index files (e.g. the Chroma DB dir).
        """
        self.index_path = Path(index_path)
        self._bm25 = None
        self._chunk_ids: list[str] = []

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(self, chunks: list[tuple[str, str]]) -> None:
        """Build and persist the BM25 index from a list of chunks.

        Args:
            chunks: Sequence of ``(chunk_id, text)`` pairs.
        """
        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

        chunk_ids = [cid for cid, _ in chunks]
        tokenised = [_tokenise(text) for _, text in chunks]

        self._bm25 = BM25Okapi(tokenised)
        self._chunk_ids = chunk_ids

        # Persist
        self.index_path.mkdir(parents=True, exist_ok=True)
        with (self.index_path / self._INDEX_FILE).open("wb") as fh:
            pickle.dump(self._bm25, fh)
        with (self.index_path / self._CHUNKS_FILE).open("w", encoding="utf-8") as fh:
            json.dump(chunk_ids, fh)

        LOGGER.info("BM25 index built with %d chunks", len(chunks))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load the index from disk.

        Returns:
            True if loaded successfully, False if files are missing.
        """
        idx_file = self.index_path / self._INDEX_FILE
        chunks_file = self.index_path / self._CHUNKS_FILE

        if not idx_file.exists() or not chunks_file.exists():
            return False

        try:
            with idx_file.open("rb") as fh:
                self._bm25 = pickle.load(fh)  # noqa: S301
            with chunks_file.open("r", encoding="utf-8") as fh:
                self._chunk_ids = json.load(fh)
            LOGGER.info("BM25 index loaded (%d chunks)", len(self._chunk_ids))
            return True
        except Exception:
            LOGGER.exception("Failed to load BM25 index")
            self._bm25 = None
            self._chunk_ids = []
            return False

    # ------------------------------------------------------------------
    # Searching
    # ------------------------------------------------------------------

    def search(self, query: str, n: int = 200) -> list[tuple[str, float]]:
        """Search the index and return ranked chunk IDs.

        Args:
            query: Query string.
            n: Maximum number of results to return.

        Returns:
            List of ``(chunk_id, normalised_score)`` tuples sorted by score
            descending.  Scores are in ``[0, 1]`` (normalised by the maximum
            score in the result set).  Returns an empty list if the index is
            not loaded or no results found.
        """
        if self._bm25 is None:
            return []

        tokens = _tokenise(query)
        raw_scores: list[float] = self._bm25.get_scores(tokens).tolist()

        # Pair with chunk IDs and sort
        scored = sorted(
            zip(self._chunk_ids, raw_scores, strict=True),
            key=lambda x: x[1],
            reverse=True,
        )
        top_n = scored[:n]

        if not top_n:
            return []

        max_score = top_n[0][1]
        if max_score <= 0:
            return [(cid, 0.0) for cid, _ in top_n]

        return [(cid, score / max_score) for cid, score in top_n]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_built(self) -> bool:
        """Return True if the index is loaded and ready."""
        return self._bm25 is not None and bool(self._chunk_ids)

    def wipe(self) -> None:
        """Delete persisted index files and reset in-memory state."""
        for fname in [self._INDEX_FILE, self._CHUNKS_FILE]:
            fpath = self.index_path / fname
            if fpath.exists():
                fpath.unlink()
        self._bm25 = None
        self._chunk_ids = []
