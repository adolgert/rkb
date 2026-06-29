"""Tests for ChunkStore."""

import pytest

from rkb.core.chunk_store import ChunkStore


@pytest.fixture
def store(tmp_path):
    return ChunkStore(tmp_path / "chunks.db")


def test_upsert_and_get_chunks(store):
    chunks = [(0, "hello"), (1, "world"), (2, "foo")]
    store.upsert_chunks("doc1", chunks)
    result = store.get_chunks("doc1", 0, 2)
    assert result == chunks


def test_get_chunks_range(store):
    store.upsert_chunks("doc1", [(i, f"chunk{i}") for i in range(5)])
    result = store.get_chunks("doc1", 1, 3)
    assert result == [(1, "chunk1"), (2, "chunk2"), (3, "chunk3")]


def test_get_chunks_empty(store):
    result = store.get_chunks("missing", 0, 10)
    assert result == []


def test_upsert_replaces_existing(store):
    store.upsert_chunks("doc1", [(0, "old")])
    store.upsert_chunks("doc1", [(0, "new")])
    result = store.get_chunks("doc1", 0, 0)
    assert result == [(0, "new")]


def test_delete_doc(store):
    store.upsert_chunks("doc1", [(0, "a"), (1, "b")])
    store.upsert_chunks("doc2", [(0, "x")])
    deleted = store.delete_doc("doc1")
    assert deleted == 2
    assert store.get_chunks("doc1", 0, 10) == []
    assert store.get_chunks("doc2", 0, 0) == [(0, "x")]


def test_delete_doc_missing(store):
    assert store.delete_doc("nobody") == 0


def test_get_chunk_count(store):
    store.upsert_chunks("doc1", [(i, f"t{i}") for i in range(7)])
    assert store.get_chunk_count("doc1") == 7
    assert store.get_chunk_count("missing") == 0
