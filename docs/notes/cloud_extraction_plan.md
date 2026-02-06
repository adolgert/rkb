# Cloud Extraction Plan: Processing 10,000 PDFs with Nougat OCR

**Status:** Planning
**Created:** 2025-09-29
**Goal:** Extract 10,000 academic PDFs to markdown using cloud GPU infrastructure

---

## Executive Summary

**Recommended Approach: Modal.com Serverless GPU**

- **Cost:** $150-300 for 10,000 files
- **Time:** 2-6 hours processing (50-100 parallel GPUs)
- **Setup:** 1-2 days implementation
- **Complexity:** Low (Python decorator-based API)

Modal.com provides the best balance of cost, speed, ease of implementation, and integration with the project-based architecture.

---

## Problem Statement

Nougat OCR processing is:
1. **GPU-intensive:** Requires NVIDIA GPU for reasonable speed
2. **Slow on single machine:** ~30s-2min per document = 83-333 hours sequential
3. **No public API exists:** Unlike Claude or Grok, no managed Nougat API available

For 10,000 files, we need cloud GPU infrastructure with parallel processing.

---

## Options Comparison

| Option | Cost | Setup Time | Processing Time | Complexity | Pros | Cons |
|--------|------|------------|-----------------|------------|------|------|
| **Replicate.com** | $810 | Immediate | ~1,167 hours | Very Low | Zero setup, ready API | Expensive, sequential, rate limits |
| **Modal.com** ⭐ | $150-300 | 1-2 days | 2-6 hours | Low | Auto-scaling, simple code | Requires wrapper code |
| **Vast.ai Spot** | $100-200 | 2-3 days | 10-15 hours | Medium | Cheapest, flexible | Manual management, spot interruptions |
| **AWS Batch** | $200-400 | 3-5 days | 8-12 hours | High | Production-grade, managed | Complex setup, AWS knowledge needed |
| **HuggingFace** | $200-500 | 2-3 days | Variable | Medium | Managed endpoint | Need to deploy, ongoing costs |

**Recommendation:** Modal.com offers the best ROI for a one-time large batch extraction.

---

## Modal.com Implementation Plan

### Architecture Overview

```
Local Machine                   Modal.com Cloud
    │                              │
    ├─ Upload PDF list             ├─ Auto-scale to 50-100 GPU instances
    │  to Modal Volume             │  (T4 or A100)
    │                              │
    ├─ Submit batch job       ────>├─ Each GPU processes PDFs in parallel
    │  (10,000 tasks)              │  └─ Nougat extraction
    │                              │  └─ Save .mmd to Volume
    │                              │
    └─ Download extractions   <────└─ Volume:/nougat_v1/extractions/
       to local project
```

### Implementation Code

**File:** `scripts/modal_nougat_batch.py`

```python
"""Modal.com batch processor for Nougat OCR extraction."""

import json
from pathlib import Path
from datetime import datetime
import tempfile
import subprocess

import modal

# Create Modal stub
stub = modal.Stub("rkb-nougat-batch")

# Define container image with Nougat installed
nougat_image = (
    modal.Image.debian_slim()
    .apt_install("git", "poppler-utils")  # poppler for PDF tools
    .pip_install(
        "nougat-ocr[api]==0.1.17",
        "PyPDF2",  # For page counting
    )
)

# Create persistent volume for PDFs and outputs
volume = modal.Volume.from_name("rkb-pdf-processing", create_if_missing=True)


@stub.function(
    image=nougat_image,
    gpu="T4",  # or "A100" for 3x faster processing
    timeout=600,  # 10 minutes per file
    volumes={"/data": volume},
    retries=2,  # Retry on failure
    concurrency_limit=100,  # Max 100 parallel executions
)
def extract_single_pdf(
    pdf_relative_path: str,
    project_name: str,
    max_pages: int = 50,
) -> dict:
    """Extract single PDF using Nougat.

    Args:
        pdf_relative_path: Path relative to /data/pdfs/
        project_name: Project directory name (e.g., "nougat_v1")
        max_pages: Maximum pages to process

    Returns:
        Result dictionary with status and metadata
    """
    start_time = datetime.now()
    pdf_path = Path("/data/pdfs") / pdf_relative_path
    pdf_name = pdf_path.stem

    # Validate PDF exists
    if not pdf_path.exists():
        return {
            "status": "error",
            "pdf_path": str(pdf_relative_path),
            "error": "PDF not found",
        }

    # Get page count
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)

        if page_count > max_pages:
            print(f"⚠️  {pdf_name}: {page_count} pages, processing first {max_pages}")
    except Exception as e:
        page_count = None
        print(f"⚠️  Could not determine page count: {e}")

    # Create output directory
    output_dir = Path("/data") / project_name / "extractions"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run Nougat extraction
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        try:
            cmd = [
                "nougat",
                str(pdf_path),
                "--out", str(tmp_path),
                "--no-skipping",  # Process all pages
            ]

            if max_pages:
                cmd.extend(["--pages", f"1-{max_pages}"])

            print(f"🔄 Processing {pdf_name}...")
            result = subprocess.run(
                cmd,
                timeout=540,  # 9 minutes (leave buffer for cleanup)
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {
                    "status": "error",
                    "pdf_path": str(pdf_relative_path),
                    "error": f"Nougat failed: {result.stderr}",
                }

            # Find output file
            mmd_files = list(tmp_path.glob("*.mmd"))
            if not mmd_files:
                return {
                    "status": "error",
                    "pdf_path": str(pdf_relative_path),
                    "error": "No .mmd output generated",
                }

            # Read extraction
            mmd_content = mmd_files[0].read_text(encoding="utf-8")

            if len(mmd_content) < 100:
                return {
                    "status": "error",
                    "pdf_path": str(pdf_relative_path),
                    "error": f"Extraction too short ({len(mmd_content)} chars)",
                }

            # Save to output directory
            output_path = output_dir / f"{pdf_name}.mmd"
            output_path.write_text(mmd_content, encoding="utf-8")

            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            print(f"✓ {pdf_name}: {len(mmd_content)} chars in {duration:.1f}s")

            return {
                "status": "success",
                "pdf_path": str(pdf_relative_path),
                "output_path": str(output_path),
                "content_length": len(mmd_content),
                "page_count": page_count,
                "duration_seconds": duration,
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "pdf_path": str(pdf_relative_path),
                "error": "Extraction timed out after 9 minutes",
            }
        except Exception as e:
            return {
                "status": "error",
                "pdf_path": str(pdf_relative_path),
                "error": str(e),
            }


@stub.function(
    volumes={"/data": volume},
    timeout=3600,  # 1 hour for orchestration
)
def process_batch(
    pdf_list_path: str,
    project_name: str,
    max_pages: int = 50,
) -> dict:
    """Process batch of PDFs in parallel.

    Args:
        pdf_list_path: Path to file with list of PDF paths (relative to /data/pdfs/)
        project_name: Project directory name
        max_pages: Maximum pages to process per PDF

    Returns:
        Summary of batch processing
    """
    start_time = datetime.now()

    # Read PDF list
    pdf_list_file = Path("/data") / pdf_list_path
    with pdf_list_file.open() as f:
        pdf_paths = [line.strip() for line in f if line.strip()]

    print(f"📋 Processing {len(pdf_paths)} PDFs...")
    print(f"   Project: {project_name}")
    print(f"   Max pages: {max_pages}")

    # Process all PDFs in parallel using .map()
    results = list(extract_single_pdf.map(
        pdf_paths,
        [project_name] * len(pdf_paths),
        [max_pages] * len(pdf_paths),
    ))

    # Analyze results
    success = [r for r in results if r["status"] == "success"]
    errors = [r for r in results if r["status"] == "error"]
    timeouts = [r for r in results if r["status"] == "timeout"]

    # Calculate statistics
    total_duration = (datetime.now() - start_time).total_seconds()

    if success:
        avg_duration = sum(r["duration_seconds"] for r in success) / len(success)
        total_chars = sum(r["content_length"] for r in success)
    else:
        avg_duration = 0
        total_chars = 0

    summary = {
        "total_pdfs": len(pdf_paths),
        "successful": len(success),
        "errors": len(errors),
        "timeouts": len(timeouts),
        "total_duration_seconds": total_duration,
        "avg_duration_per_pdf": avg_duration,
        "total_extracted_chars": total_chars,
        "error_details": errors[:10],  # First 10 errors
    }

    # Save summary
    summary_path = Path("/data") / project_name / "extraction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print("\n" + "="*60)
    print(f"✓ Batch Complete!")
    print(f"  Success: {len(success)}/{len(pdf_paths)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Timeouts: {len(timeouts)}")
    print(f"  Total time: {total_duration/60:.1f} minutes")
    print(f"  Avg per PDF: {avg_duration:.1f} seconds")
    print("="*60)

    return summary


@stub.local_entrypoint()
def main(
    pdf_list: str,
    project_name: str = "nougat_v1_cloud",
    max_pages: int = 50,
):
    """Entry point for batch processing.

    Usage:
        modal run modal_nougat_batch.py --pdf-list pdf_paths.txt --project-name nougat_v1
    """
    # Upload PDF list to volume if it's local
    local_pdf_list = Path(pdf_list)
    if local_pdf_list.exists():
        print(f"📤 Uploading PDF list to Modal Volume...")
        volume.commit()  # Ensure volume is available
        # Copy file to volume
        # Note: Would need to implement upload logic here
        remote_pdf_list = "pdf_list.txt"
    else:
        remote_pdf_list = pdf_list

    # Run batch processing
    with stub.run():
        result = process_batch.remote(
            remote_pdf_list,
            project_name,
            max_pages
        )

    print(f"\n✅ Processing complete! Check /data/{project_name}/extractions/")
    return result
```

### Step-by-Step Deployment

#### 1. Install Modal

```bash
pip install modal
modal setup  # Authenticate with Modal (creates free account)
```

#### 2. Upload PDFs to Modal Volume

```bash
# Create volume
modal volume create rkb-pdf-processing

# Upload PDFs (this may take a while for 10,000 files)
modal volume put rkb-pdf-processing ./data/pdfs/ /pdfs/

# Verify upload
modal volume ls rkb-pdf-processing /pdfs/ | head -20
```

#### 3. Create PDF List File

```bash
# List all PDFs (relative paths)
cd data/pdfs/
find . -name "*.pdf" | sed 's|^\./||' > ../../pdf_paths.txt
cd ../..

# Upload list to Modal
modal volume put rkb-pdf-processing pdf_paths.txt /pdf_list.txt
```

#### 4. Run Batch Processing

```bash
# Process with T4 GPUs (cheaper)
modal run scripts/modal_nougat_batch.py \
  --pdf-list /pdf_list.txt \
  --project-name nougat_v1_cloud \
  --max-pages 50

# Or with A100 GPUs (3x faster, ~same cost due to shorter runtime)
# Edit script: gpu="A100" instead of gpu="T4"
modal run scripts/modal_nougat_batch.py \
  --pdf-list /pdf_list.txt \
  --project-name nougat_v1_cloud
```

#### 5. Monitor Progress

```bash
# Check Modal dashboard
open https://modal.com/apps

# View logs in real-time
modal app logs rkb-nougat-batch

# Check partial results
modal volume ls rkb-pdf-processing /nougat_v1_cloud/extractions/ | wc -l
```

#### 6. Download Results

```bash
# Download all extractions to local project
modal volume get rkb-pdf-processing \
  /nougat_v1_cloud/extractions/ \
  ./projects/nougat_v1_cloud/extractions/

# Download summary
modal volume get rkb-pdf-processing \
  /nougat_v1_cloud/extraction_summary.json \
  ./projects/nougat_v1_cloud/
```

---

## Integration with RKB Project Architecture

### Create Project from Cloud Extractions

Once extractions are downloaded, integrate into RKB:

```python
# scripts/import_cloud_extractions.py
from pathlib import Path
from rkb.core.project_registry import ProjectRegistry
from rkb.core.document_registry import DocumentRegistry

def import_cloud_extractions(
    extractions_dir: Path,
    pdfs_dir: Path,
    project_name: str
):
    """Import cloud-extracted files into RKB project.

    Args:
        extractions_dir: Directory with .mmd files from Modal
        pdfs_dir: Directory with source PDFs
        project_name: Name for RKB project
    """
    # Create project
    registry = ProjectRegistry()
    project = registry.create_project(project_name, {
        "name": "nougat",
        "version": "0.1.17",
        "extracted_on": "modal_cloud",
        "notes": "Batch extracted on Modal.com"
    })

    # Import each extraction
    doc_registry = project.extraction_registry

    mmd_files = list(extractions_dir.glob("*.mmd"))
    print(f"Found {len(mmd_files)} extractions")

    for mmd_file in mmd_files:
        # Find corresponding PDF
        pdf_name = mmd_file.stem
        pdf_path = pdfs_dir / f"{pdf_name}.pdf"

        if not pdf_path.exists():
            print(f"⚠️  PDF not found: {pdf_name}")
            continue

        # Register document
        from rkb.core.text_processing import hash_file
        content_hash = hash_file(pdf_path)

        # Check if already exists
        existing = doc_registry.find_by_content_hash(content_hash)
        if existing:
            print(f"⏭️  Skipping duplicate: {pdf_name}")
            continue

        # Read extraction
        content = mmd_file.read_text(encoding="utf-8")

        # Add to project database
        doc_id = doc_registry.register_document(
            source_path=pdf_path,
            content_hash=content_hash,
        )

        # Store extraction
        from rkb.core.models import ExtractionResult, ExtractionStatus
        extraction = ExtractionResult(
            doc_id=doc_id,
            extraction_id=f"{doc_id}_cloud",
            status=ExtractionStatus.COMPLETE,
            content=content,
            extractor_name="nougat",
            extractor_version="0.1.17",
        )

        doc_registry.add_extraction(extraction)
        print(f"✓ Imported: {pdf_name}")

    print(f"\n✅ Imported {len(mmd_files)} documents into {project_name}")

if __name__ == "__main__":
    import_cloud_extractions(
        extractions_dir=Path("projects/nougat_v1_cloud/extractions"),
        pdfs_dir=Path("data/pdfs"),
        project_name="nougat_v1_cloud"
    )
```

**Run import:**
```bash
python scripts/import_cloud_extractions.py
```

### Create Experiments from Cloud Extractions

Once imported into project, create experiments normally:

```bash
# Create baseline experiment
rkb experiment create nougat_v1_cloud baseline --chunk-size 2000

# Create large-chunk experiment
rkb experiment create nougat_v1_cloud large_chunks --chunk-size 4000

# Search within experiments
rkb search --project nougat_v1_cloud --experiment baseline "neural networks"
```

---

## Cost & Timeline Estimates

### Modal.com Costs

**T4 GPU Processing:**
- GPU rate: ~$0.60/hour
- Processing speed: ~1.5 min/document (including retries)
- Total GPU-minutes: 10,000 × 1.5 = 15,000 minutes
- Total GPU-hours: 15,000 / 60 = 250 hours
- **Parallel processing:** With 100 concurrent GPUs = 2.5 hours wall-clock time
- **Cost:** 250 × $0.60 = **$150**

**A100 GPU Processing:**
- GPU rate: ~$1.85/hour
- Processing speed: ~0.5 min/document (3x faster than T4)
- Total GPU-minutes: 10,000 × 0.5 = 5,000 minutes
- Total GPU-hours: 5,000 / 60 = 83 hours
- **Parallel processing:** With 100 concurrent GPUs = 0.83 hours wall-clock time
- **Cost:** 83 × $1.85 = **$154**

**Recommendation:** Use A100 - similar cost, 3x faster, less time to monitor.

### Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Setup | 4-8 hours | Write Modal wrapper, test with 10 files |
| PDF Upload | 2-6 hours | Upload 10,000 PDFs to Modal Volume |
| Processing | 1-3 hours | Batch extraction with 100 parallel GPUs |
| Download | 1-2 hours | Download .mmd files from Modal |
| Import | 1-2 hours | Import into RKB project structure |
| **Total** | **1-2 days** | End-to-end implementation |

---

## Error Handling & Recovery

### Built-in Retry Logic

Modal function retries (configured with `retries=2`):
1. First attempt fails → automatic retry #1
2. Retry #1 fails → automatic retry #2
3. Retry #2 fails → return error result

### Resumability

If batch processing is interrupted:

```python
# Check what succeeded
import json
summary = json.loads(Path("projects/nougat_v1_cloud/extraction_summary.json").read_text())
successful_pdfs = set(r["pdf_path"] for r in summary["results"] if r["status"] == "success")

# Create list of remaining PDFs
all_pdfs = Path("pdf_paths.txt").read_text().splitlines()
remaining = [p for p in all_pdfs if p not in successful_pdfs]

# Save remaining list
Path("pdf_paths_remaining.txt").write_text("\n".join(remaining))

# Resume processing
modal run scripts/modal_nougat_batch.py \
  --pdf-list /pdf_paths_remaining.txt \
  --project-name nougat_v1_cloud
```

### Failure Analysis

After processing, analyze failures:

```python
# Load summary
summary = json.load(open("projects/nougat_v1_cloud/extraction_summary.json"))

# Group errors by type
from collections import Counter
error_types = Counter(r["error"].split(":")[0] for r in summary["error_details"])

print("Error breakdown:")
for error_type, count in error_types.most_common():
    print(f"  {error_type}: {count}")

# Retry specific error types
timeout_pdfs = [r["pdf_path"] for r in summary["results"]
                if r["status"] == "timeout"]
```

---

## Alternative Approach: Vast.ai DIY

For maximum cost savings with more DevOps work:

### Vast.ai Setup

1. **Rent GPU instances:**
   ```bash
   # Search for cheap A100 spot instances
   vastai search offers 'gpu_name=A100 num_gpus=1' --order 'dph+'

   # Rent 10 instances
   for i in {1..10}; do
     vastai create instance <INSTANCE_ID> --image nvidia/cuda:11.8.0-runtime-ubuntu22.04
   done
   ```

2. **Deploy Nougat container:**
   ```bash
   # SSH into each instance
   vastai ssh <INSTANCE_ID>

   # Install Nougat
   pip install nougat-ocr[api]

   # Mount S3 or shared storage
   apt-get install awscli
   aws configure
   ```

3. **Distribute work:**
   ```bash
   # Split PDF list into 10 chunks
   split -n l/10 pdf_paths.txt pdf_chunk_

   # On each instance, process assigned chunk
   cat pdf_chunk_aa | parallel -j 4 \
     'nougat /s3-mount/pdfs/{} --out /s3-mount/output/'
   ```

**Pros:** Cheapest option (~$100-150)
**Cons:** Manual setup, monitoring, spot interruption handling

---

## Comparison Summary

| Metric | Modal (Recommended) | Vast.ai DIY |
|--------|---------------------|-------------|
| **Cost** | $150-300 | $100-200 |
| **Setup Time** | 1-2 days | 2-3 days |
| **Processing Time** | 1-3 hours | 10-15 hours |
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Reliability** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Monitoring** | Built-in dashboard | Manual |
| **Resumability** | Automatic | Manual |

**Recommendation:** Use Modal.com unless you're comfortable with DevOps and want to save $50-100.

---

## Next Steps

1. ✅ Review this plan
2. Install Modal: `pip install modal && modal setup`
3. Test with 10 PDFs to validate approach
4. Upload all PDFs to Modal Volume
5. Run batch processing
6. Download and import into RKB project
7. Create experiments and begin semantic search testing

**Estimated total time:** 2-3 days from start to searchable database.

---

## Questions & Considerations

### What about page number tracking?

The cloud extraction produces `.mmd` files without explicit page markers. However:
- The robustness plan (Phase 1.2) includes approximate page number extraction
- Page numbers can be estimated from content length (~2000 chars/page)
- This is good enough for initial extraction
- Can improve later without re-extracting

### Can we process while building robustness features?

Yes! The workflow is:
1. **Week 1:** Implement Modal extraction (this plan) + upload PDFs
2. **Week 1-2:** Process 10,000 PDFs in background (1-3 hours processing + time to upload/download)
3. **Week 2-3:** Implement robustness features (Phase 1-3 of robustness plan)
4. **Week 3:** Import cloud extractions into robust project structure
5. **Week 3+:** Create experiments and begin semantic search work

### What if Modal doesn't work out?

Fallback options:
1. Try Replicate.com (more expensive but zero setup)
2. Use Vast.ai (cheaper but more work)
3. Process locally in background (takes weeks but costs nothing)

The Modal approach has the best risk/reward profile.