# Rectification: `rkb rectify`

## Purpose

One-time reconciliation of existing PDF collections. Scans all known PDF
locations (Dropbox/Mendeley, Zotero storage, Downloads, etc.), deduplicates by
content hash, and ensures the canonical store and Zotero are complete.

This command is designed for the initial migration from the current state
(2000+ PDFs scattered across directories) to the target state (every unique PDF
in both the canonical Dropbox store and Zotero). After rectification, the
ongoing `rkb ingest` command maintains the target state incrementally.

## Command Interface

```bash
rkb rectify --scan ~/Dropbox/Mendeley ~/Zotero/storage ~/Downloads
rkb rectify --dry-run --scan ~/Dropbox/Mendeley
rkb rectify --report --scan ~/Dropbox/Mendeley ~/Zotero/storage
rkb rectify --skip-zotero --scan ~/Dropbox/Mendeley
```

### Arguments

| Argument/Flag | Description |
|---------------|-------------|
| `--scan DIRS...` | Directories to scan for existing PDFs |
| `--dry-run` | Report what would happen without copying or importing |
| `--report` | Show gap analysis only (fast: hash + compare, no copies or API calls) |
| `--skip-zotero` | Only ensure canonical store completeness; skip Zotero |
| `--json` | Machine-readable output |
| `--verbose` | Per-file details |

### Exit codes

Same as `rkb ingest`: 0 success, 1 error, 2 partial success.

## Processing Flow

### Step 1: Discovery

Scan all specified directories recursively for `.pdf` files. For each file:
- Compute SHA-256.
- Record page count and file size (best effort).
- Record source path and machine ID.

This step can take a while for 2000+ files. Progress reporting (a progress bar
or periodic count updates) is important.

### Step 2: Deduplication Report

Group all discovered files by hash. Report:
- Total files found.
- Unique PDFs (distinct hashes).
- Duplicate files (same hash, different paths). For each duplicate group, list
  all paths.

### Step 3: Canonical Store -- Forward Gap

For each unique hash:
- Is it already in the canonical store?
  - **Yes:** Record a source sighting. Done.
  - **No:** Copy to canonical store (generate display name). Record in catalog.

### Step 4: Canonical Store -- Reverse Gap

Are there PDFs in Zotero storage (or other scanned dirs) that are NOT in the
canonical store? This is the reverse check: making sure the canonical store is
truly complete.

For each file in `~/Zotero/storage/` whose hash is not in the catalog:
- Copy it from Zotero storage to the canonical store.
- Record in catalog with source type noting it came from Zotero.

### Step 5: Zotero Gap Analysis (unless `--skip-zotero`)

For each unique hash in the catalog:
- Is it in Zotero? (Check against hash scan of Zotero storage.)
  - **Yes:** Record as `pre-existing`.
  - **No:** Queue for Zotero import.

### Step 6: Execute

Unless `--dry-run` or `--report`:
- Copy files to canonical store.
- Import queued files to Zotero (unless `--skip-zotero`).
- Update catalog.

### Output

```
Discovery:
  Scanned directories:                        3
  Total PDF files found:                  3,847
  Unique PDFs (by hash):                  2,512
  Duplicate files:                        1,335

Canonical Store:
  Already in store:                       1,200
  New (will copy):                        1,312

Zotero:
  Already in Zotero:                      1,800
  Not in Zotero (will import):              712
  In Zotero but not in store (will copy):    45

Actions taken:
  Copied to canonical store:              1,357   (1,312 from scanned + 45 from Zotero)
  Imported to Zotero:                       712
  Failures:                                   3
```

## Relationship to `rkb ingest`

Rectify reuses the same core logic as ingest (hashing, canonical store copy,
Zotero import). The differences are:

| | `rkb ingest` | `rkb rectify` |
|--|-------------|--------------|
| Use case | Daily: process new PDFs from an inbox | One-time: reconcile existing collections |
| Source dirs | Inbox directories | All known PDF locations |
| Direction | Forward only (inbox -> store -> Zotero) | Bidirectional (also Zotero -> store) |
| Dedup report | Per-file (new/duplicate/failed) | Collection-wide (duplicate groups, gap analysis) |
| Progress | Brief summary | Detailed report with progress bar |

Both commands are idempotent: running rectify twice shows everything as
already present on the second run.

## Performance Considerations

Hashing 2000+ PDFs (many of which may be large) takes meaningful time. Consider:
- Showing a progress bar with estimated time remaining.
- Caching hash results in the catalog's `source_sightings` table so that
  files seen before (same path, same mtime, same size) can skip re-hashing.
- Processing in a predictable order (alphabetical by path) so that if the
  process is interrupted, progress is visible and roughly resumable.

Zotero import of hundreds of files will hit API rate limits. The Zotero sync
module must handle this gracefully (see ZOTERO_INTEGRATION.md).

## Dependencies

- Core library (all modules)
- Zotero sync module
- Ingest logic (rectify composes the same operations)

## Verification

1. **Integration test.** Create a mock filesystem with:
   - A "Mendeley" directory with some PDFs.
   - A "Zotero storage" directory with some overlapping and some unique PDFs.
   - A "Downloads" directory with some overlapping PDFs.
   Run rectify. Verify:
   - Canonical store contains every unique hash exactly once.
   - Zotero links are recorded for all files.
   - Duplicate groups are correctly identified.

2. **Dry-run test.** Run with `--dry-run`. Verify the report is accurate but
   no files are copied and no database records are created.

3. **Report-only test.** Run with `--report`. Verify it produces gap analysis
   without any copies or API calls.

4. **Idempotency test.** Run rectify twice. Verify the second run reports
   everything as already present with zero actions taken.

5. **Bidirectional test.** Create a file that exists in mock Zotero storage but
   not in the canonical store. Verify rectify copies it to the canonical store.
