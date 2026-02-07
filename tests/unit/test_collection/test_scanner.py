"""Tests for directory PDF scanning."""

from pathlib import Path

import pytest

from rkb.collection.scanner import scan_pdf_files


def test_scan_pdf_files_recurses_and_filters(tmp_path):
    inbox = tmp_path / "inbox"
    nested = inbox / "nested"
    nested.mkdir(parents=True)

    first_pdf = inbox / "first.pdf"
    second_pdf = nested / "second.PDF"
    ignored_file = nested / "note.txt"

    first_pdf.write_bytes(b"one")
    second_pdf.write_bytes(b"two")
    ignored_file.write_text("ignore", encoding="utf-8")

    scanned = scan_pdf_files([inbox])

    assert scanned == sorted([first_pdf.resolve(), second_pdf.resolve()], key=str)


def test_scan_pdf_files_raises_for_missing_directory(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        scan_pdf_files([missing])


def test_scan_pdf_files_raises_for_non_directory(tmp_path):
    pdf_path = tmp_path / "just-a-file.pdf"
    pdf_path.write_bytes(b"bytes")

    with pytest.raises(NotADirectoryError):
        scan_pdf_files([Path(pdf_path)])

