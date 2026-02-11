"""Tests for display-name generation."""

from rkb.collection.display_name import generate_display_name


def test_generate_display_name_from_metadata(tmp_path):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"fake pdf")
    metadata = {
        "author": "Jane Smith and Bob Jones",
        "year": 2024,
        "title": "Bayesian survival analysis",
    }

    name = generate_display_name(pdf_path, metadata)

    assert name == "Smith 2024 Bayesian survival analysis.pdf"


def test_generate_display_name_from_first_page_text(monkeypatch, tmp_path):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"fake pdf")

    monkeypatch.setattr(
        "rkb.collection.display_name._extract_first_page_text",
        lambda _path: "A Great Paper\nJohn Doe\nPublished in 2022",
    )

    name = generate_display_name(pdf_path)

    assert name == "Doe 2022 A Great Paper.pdf"


def test_generate_display_name_falls_back_to_original_filename(tmp_path):
    pdf_path = tmp_path / "mü$ paper?.pdf"
    pdf_path.write_bytes(b"fake pdf")

    name = generate_display_name(pdf_path)

    assert name.endswith(".pdf")
    assert " " in name
    assert "*" not in name
    assert "?" not in name


def test_generate_display_name_truncates_long_names(tmp_path):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"fake pdf")
    metadata = {
        "author": "Ada Lovelace",
        "year": "2025",
        "title": "X" * 200,
    }

    name = generate_display_name(pdf_path, metadata)

    assert len(name) <= 120
    assert name.endswith(".pdf")
