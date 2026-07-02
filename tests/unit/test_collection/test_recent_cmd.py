"""Tests for the recent CLI command handler."""

import argparse
import json

from rkb.cli.commands import recent_cmd
from rkb.collection.catalog import Catalog


def _make_args(**overrides):
    defaults = {"limit": 20, "json": False, "config": None, "verbose": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _seed_catalog(library_root, entries):
    catalog = Catalog(library_root / "db" / "pdf_catalog.db")
    catalog.initialize()
    for sha, display_name in entries:
        catalog.add_canonical_file(
            content_sha256=sha,
            canonical_path=str(library_root / "sha256" / sha[:2] / sha[2:4] / sha / display_name),
            display_name=display_name,
            original_filename=display_name,
            page_count=10,
            file_size_bytes=1000,
        )
    catalog.close()


def test_recent_lists_newest_first_with_links(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))

    older = "a" * 64
    newer = "b" * 64
    _seed_catalog(library_root, [(older, "Older Paper.pdf"), (newer, "Newer Paper.pdf")])

    # Give the newer document a Markdown extraction.
    extraction_dir = (
        library_root / "sha256" / newer[:2] / newer[2:4] / newer / "extractions" / "marker-pdf-1.0"
    )
    extraction_dir.mkdir(parents=True)
    (extraction_dir / "extracted.md").write_text("# Newer Paper")

    exit_code = recent_cmd.execute(_make_args())
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert stdout.index("Newer Paper") < stdout.index("Older Paper")
    assert "file://" in stdout
    assert "Newer%20Paper.pdf" in stdout
    assert "extracted.md" in stdout
    assert "(not translated yet)" in stdout


def test_recent_json_output(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))

    sha = "c" * 64
    _seed_catalog(library_root, [(sha, "Some Paper.pdf")])

    exit_code = recent_cmd.execute(_make_args(json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(payload) == 1
    assert payload[0]["content_sha256"] == sha
    assert payload[0]["display_name"] == "Some Paper.pdf"
    assert payload[0]["extraction_path"] is None


def test_recent_respects_limit(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))

    entries = [(str(i) * 64, f"Paper {i}.pdf") for i in range(1, 6)]
    _seed_catalog(library_root, entries)

    exit_code = recent_cmd.execute(_make_args(limit=2, json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(payload) == 2
    # Insertion order ties on timestamp resolve to newest row first.
    assert payload[0]["display_name"] == "Paper 5.pdf"


def test_recent_empty_catalog(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))

    exit_code = recent_cmd.execute(_make_args())
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "No documents" in stdout
