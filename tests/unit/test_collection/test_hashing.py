"""Tests for collection hashing helpers."""

import hashlib

from rkb.collection.hashing import hash_file_sha256


def test_hash_file_sha256_matches_hashlib(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    payload = b"example pdf bytes"
    pdf_path.write_bytes(payload)

    expected = hashlib.sha256(payload).hexdigest()
    actual = hash_file_sha256(pdf_path)

    assert actual == expected


def test_hash_file_sha256_is_stable(tmp_path):
    pdf_path = tmp_path / "stable.pdf"
    pdf_path.write_bytes(b"stable content")

    first = hash_file_sha256(pdf_path)
    second = hash_file_sha256(pdf_path)

    assert first == second


def test_hash_file_sha256_differs_for_different_files(tmp_path):
    first_path = tmp_path / "one.pdf"
    second_path = tmp_path / "two.pdf"
    first_path.write_bytes(b"content one")
    second_path.write_bytes(b"content two")

    assert hash_file_sha256(first_path) != hash_file_sha256(second_path)

