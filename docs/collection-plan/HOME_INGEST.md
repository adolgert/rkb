# Home Ingest: `rkb ingest`

## Purpose

Take PDFs from one or more inbox directories, deduplicate, copy each new one
into the canonical Dropbox store, and optionally import into Zotero. This is
the daily-use command on the home machine.

## Command Interface

```bash
rkb ingest ~/Documents/box-staging/
rkb ingest ~/Downloads/ ~/Documents/box-staging/
rkb ingest --dry-run ~/Documents/box-staging/
rkb ingest --skip-zotero ~/Downloads/
rkb ingest --no-display-name ~/Documents/box-staging/
rkb ingest --json ~/Documents/box-staging/
```

### Arguments

| Argument/Flag | Description |
|---------------|-------------|
| `DIRECTORIES...` | One or more directories to scan for PDFs (recursive) |
| `--dry-run` | Report what would happen without copying or importing anything |
| `--skip-zotero` | Copy to canonical store only; do not import into Zotero |
| `--no-display-name` | Use original filename instead of generating a display name |
| `--json` | Machine-readable JSON output |
| `--verbose` | Show per-file details |

### Exit codes

- `0`: all files processed successfully
- `1`: operational error (bad arguments, unreadable directory)
- `2`: partial success (some files failed; details in output)

## Processing Flow

For each `.pdf` file found recursively in the source directories:

1. **Hash** -- compute SHA-256 of the file.
2. **Catalog check** -- `catalog.is_known(hash)`.
   - Already known: log as `skipped_duplicate`, record a new source sighting
     for provenance, move to next file.
3. **Page count** -- read with PyPDF or PyMuPDF to get page count (best effort;
   failure here does not block ingestion).
4. **Generate display name** -- unless `--no-display-name`.
5. **Copy to canonical store** -- `canonical_store.store_pdf(...)`. The store
   module verifies copy integrity by re-hashing the destination.
6. **Record in catalog** -- `catalog.add_canonical_file(...)`.
7. **Record source sighting** -- `catalog.add_source_sighting(...)`.
8. **Zotero import** (unless `--skip-zotero`):
   - Check if hash exists in Zotero already (via hash scan of Zotero storage).
   - If already in Zotero: record as `pre-existing` in `zotero_links`.
   - If not in Zotero: import via pyzotero, record the item key.
9. **Log** -- `catalog.log_action(...)`.

### Human-readable output

```
Scanned: 14 files in 2 directories
  New:          8  (copied to canonical store)
  Duplicate:    5  (already in catalog)
  Failed:       1

Zotero:
  Already there:  3
  Imported:       5

Failures:
  ~/Documents/box-staging/corrupted.pdf -- could not read PDF
```

### JSON output

```json
{
  "scanned": 14,
  "new": 8,
  "duplicate": 5,
  "failed": 1,
  "zotero_imported": 5,
  "zotero_existing": 3,
  "failures": [
    {"path": "~/Documents/box-staging/corrupted.pdf", "error": "could not read PDF"}
  ]
}
```

## Idempotency

Running `rkb ingest` twice on the same directory produces the same end state.
The second run reports all files as duplicates and performs no copies or imports.
Source sightings are updated with `last_seen` timestamps.

## Source file handling

The ingest command never moves, renames, or deletes source files. After a
successful ingest, the user decides when to clean up the inbox. This is
deliberate: automatic deletion of source files is the kind of "helpful" behavior
that causes data loss.

## Error handling

- An unreadable PDF (corrupted, encrypted, zero bytes) is logged as a failure
  and does not block processing of other files.
- A Zotero API failure for one file is logged and does not block other files.
  The file is still copied to the canonical store; Zotero import can be retried
  later.
- If the canonical store directory is not writable, the command fails
  immediately with exit code 1 (this is an operational error, not a per-file
  failure).

## Implementation location

- Scanner logic: `rkb/collection/scanner.py` (discover PDFs in directories)
- Ingest orchestration: `rkb/collection/ingest.py` (the flow above)
- CLI entry point: `rkb/cli/commands/ingest_cmd.py`
- Wired into `rkb/cli/main.py` as the `ingest` subcommand

## Dependencies

- Core library: hashing, canonical_store, catalog, display_name, config
- Zotero sync module (for Zotero import step; can be deferred with
  `--skip-zotero`)

## Verification

1. **Unit tests**: Mock the catalog and canonical store. Verify the flow logic
   handles new files, duplicates, and failures correctly. Verify source
   sightings are recorded for both new and duplicate files.

2. **Integration test**: Create a temp directory with sample PDFs, create a temp
   canonical store, run ingest, verify files appear in the store with correct
   directory structure and display names. Run again; verify no changes and all
   reported as duplicate.

3. **Dry-run test**: Run with `--dry-run`; verify nothing is copied and no
   database records are created.

4. **Failure test**: Include an unreadable file in the source directory. Verify
   it is reported as failed, other files are still processed, and exit code
   is 2 (partial success).

5. **Zotero test**: With pyzotero mocked, verify import is called for new files
   and skipped for files whose hash matches a Zotero storage file.
