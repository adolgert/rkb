"""Diagnostic tests to identify nougat extraction failures.

These tests probe the actual errors by running single-page extractions
with full error output capture.
"""

import logging
import subprocess
from pathlib import Path

import pytest


@pytest.mark.system
def test_nougat_cli_single_page(sample_pdfs):
    """Test if nougat CLI works on a single page - should be fast."""
    import tempfile

    pdf_path = sample_pdfs[0]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["nougat", str(pdf_path), "--out", tmpdir, "--pages", "1-1"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        print(f"\n=== NOUGAT CLI SINGLE PAGE TEST ===")
        print(f"PDF: {pdf_path.name}")
        print(f"Return code: {result.returncode}")
        print(f"\nSTDOUT:\n{result.stdout}")
        print(f"\nSTDERR:\n{result.stderr}")

        output_file = Path(tmpdir) / f"{pdf_path.stem}.mmd"
        print(f"\nOutput file exists: {output_file.exists()}")

        if output_file.exists():
            content = output_file.read_text()
            print(f"Content length: {len(content)} chars")
            print(f"First 200 chars:\n{content[:200]}")
            assert len(content) > 0, "Output file is empty"
        else:
            print(f"Files created: {list(Path(tmpdir).iterdir())}")

        assert result.returncode == 0, f"Nougat CLI failed with code {result.returncode}"


@pytest.mark.system
def test_nougat_extractor_single_page_with_logging(temp_workspace, sample_pdfs, caplog):
    """Test NougatExtractor on single page with DEBUG logging."""
    from rkb.extractors.nougat_extractor import NougatExtractor

    # Enable DEBUG logging
    caplog.set_level(logging.DEBUG)

    pdf_path = sample_pdfs[0]

    extractor = NougatExtractor(
        chunk_size=1,
        max_pages=1,  # Only 1 page
        output_dir=temp_workspace["extraction_dir"]
    )

    print(f"\n=== NOUGAT EXTRACTOR SINGLE PAGE TEST ===")
    print(f"PDF: {pdf_path.name}")
    print(f"Extraction dir: {temp_workspace['extraction_dir']}")

    result = extractor.extract(pdf_path, doc_id="test_doc_001")

    print(f"\nExtraction status: {result.status.value}")
    print(f"Error message: {result.error_message}")
    print(f"Content length: {len(result.content) if result.content else 0}")

    # Print DEBUG logs to see subprocess details
    print("\n=== DEBUG LOGS (subprocess details) ===")
    for record in caplog.records:
        if record.levelname == "DEBUG":
            print(f"{record.message}")

    # Print WARNING logs to see what failed
    print("\n=== WARNING LOGS (failures) ===")
    for record in caplog.records:
        if record.levelname == "WARNING":
            print(f"{record.message}")

    if result.content:
        print(f"\nContent preview:\n{result.content[:300]}")


@pytest.mark.system
def test_extract_chunk_catches_exception(temp_workspace, sample_pdfs):
    """Test _extract_chunk and catch the actual exception with full details."""
    from rkb.extractors.nougat_extractor import NougatExtractor

    pdf_path = sample_pdfs[0]

    extractor = NougatExtractor(
        chunk_size=1,
        max_pages=1,
        output_dir=temp_workspace["extraction_dir"]
    )

    print(f"\n=== EXTRACT CHUNK EXCEPTION TEST ===")
    print(f"PDF: {pdf_path.name}")

    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            content = extractor._extract_chunk(pdf_path, 1, 1, temp_path)
            print(f"✓ SUCCESS: Extracted {len(content)} characters")
            print(f"Content preview:\n{content[:200]}")
        except RuntimeError as e:
            print(f"✗ RuntimeError caught: {str(e)}")
            print(f"This is the analyzed error from _analyze_chunk_error")
        except Exception as e:
            print(f"✗ EXCEPTION TYPE: {type(e).__name__}")
            print(f"✗ EXCEPTION MESSAGE: {str(e)}")
            import traceback
            print(f"\nFull traceback:")
            traceback.print_exc()
            raise


@pytest.mark.system
def test_subprocess_exact_replication(sample_pdfs):
    """Replicate the exact subprocess call from _extract_chunk."""
    pdf_path = sample_pdfs[0]

    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # This is the exact command from line 284-291 of nougat_extractor.py
        cmd = [
            "nougat",
            str(pdf_path),
            "--out",
            str(temp_path),
            "--pages",
            "1-1",
        ]

        print(f"\n=== EXACT SUBPROCESS REPLICATION TEST ===")
        print(f"PDF: {pdf_path.name}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Working dir: {Path.cwd()}")
        print(f"Output dir: {temp_path}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        print(f"\nReturn code: {result.returncode}")
        print(f"\n--- STDOUT ---\n{result.stdout}")
        print(f"\n--- STDERR ---\n{result.stderr}")

        expected_output = temp_path / f"{pdf_path.stem}.mmd"
        print(f"\nExpected output: {expected_output}")
        print(f"File exists: {expected_output.exists()}")

        if result.returncode == 0 and expected_output.exists():
            content = expected_output.read_text(encoding="utf-8").strip()
            print(f"✓ Content extracted: {len(content)} chars")
            print(f"Preview:\n{content[:300]}")
        else:
            print(f"✗ Extraction failed")
            print(f"Files in output dir: {list(temp_path.iterdir())}")

        assert result.returncode == 0, f"Subprocess failed with return code {result.returncode}"


@pytest.mark.system
def test_compare_working_vs_failing(sample_pdfs, temp_workspace):
    """Compare a known-working nougat call vs what the extractor does."""
    pdf_path = sample_pdfs[0]

    print(f"\n=== COMPARISON TEST ===")
    print(f"PDF: {pdf_path.name}")

    # Test 1: Direct nougat call (known to work)
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir1:
        print("\n--- Test 1: Direct nougat CLI ---")
        result1 = subprocess.run(
            ["nougat", str(pdf_path), "--out", tmpdir1, "--pages", "1-1"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(f"Return code: {result1.returncode}")
        output1 = Path(tmpdir1) / f"{pdf_path.stem}.mmd"
        success1 = result1.returncode == 0 and output1.exists()
        print(f"Success: {success1}")
        if success1:
            print(f"Content: {len(output1.read_text())} chars")

    # Test 2: Using NougatExtractor
    print("\n--- Test 2: NougatExtractor ---")
    from rkb.extractors.nougat_extractor import NougatExtractor

    extractor = NougatExtractor(
        chunk_size=1,
        max_pages=1,
        output_dir=temp_workspace["extraction_dir"]
    )
    result2 = extractor.extract(pdf_path, doc_id="compare_test")
    success2 = result2.status.value == "complete"
    print(f"Status: {result2.status.value}")
    print(f"Success: {success2}")
    if result2.content:
        print(f"Content: {len(result2.content)} chars")
    if result2.error_message:
        print(f"Error: {result2.error_message}")

    print(f"\n--- COMPARISON RESULT ---")
    print(f"Direct CLI works: {success1}")
    print(f"NougatExtractor works: {success2}")

    if success1 and not success2:
        print("\n⚠️  ISSUE FOUND: Direct CLI works but NougatExtractor fails!")
        print("This suggests a problem in how NougatExtractor calls nougat.")
