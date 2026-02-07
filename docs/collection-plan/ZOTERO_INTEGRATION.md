# Zotero Integration

## Purpose

Ensure every PDF in the canonical Dropbox store also exists in Zotero, without
creating duplicate Zotero entries. Zotero is the reading and metadata layer;
the canonical store is the source of truth for file bytes.

## The Duplication Problem

Zotero does not deduplicate PDFs well. Dragging the same PDF into Zotero twice
creates two separate items. Additionally, Zotero entries sometimes lose their
PDF attachment (the metadata survives but the file is gone). We need to handle
both cases:

1. **PDF already in Zotero:** Do not create a duplicate. Detect by hash.
2. **Zotero entry exists but lost its PDF:** Re-attach from the canonical store.
   (Deferred to a later phase.)

## Strategy

### Phase 1: Hash-Based Duplicate Detection (Build First)

Before importing anything, determine what Zotero already has.

1. Scan `~/Zotero/storage/**/*.pdf` recursively.
2. Compute SHA-256 of every PDF found.
3. Build an in-memory set: `zotero_known_hashes`.
4. Cache this result. Invalidate when the Zotero storage directory tree has
   changed (check root directory mtime, or re-scan periodically).

For each PDF the ingest command wants to import:
- Hash is in `zotero_known_hashes` -> skip, record as `pre-existing` in
  `zotero_links`.
- Hash is not in `zotero_known_hashes` -> import via pyzotero.

This phase requires no Zotero API credentials for the detection step (it reads
local files). Credentials are only needed for the import step.

### Phase 2: Import via pyzotero

For PDFs that need to be added to Zotero:

```python
from pyzotero import zotero

zot = zotero.Zotero(library_id, library_type, api_key)

# Create a new item with a placeholder title
template = zot.item_template('document')
template['title'] = display_name  # e.g., "Smith 2024 Bayesian survival"
created = zot.create_items([template])

# Attach the canonical PDF to the new item
item_key = created['successful']['0']['key']
zot.attachment_simple([str(canonical_pdf_path)], item_key)
```

After import, the user triggers Zotero's built-in "Retrieve Metadata for PDF"
manually in the Zotero UI. This populates the abstract and other bibliographic
fields. We accept this manual step for now because:
- Zotero's metadata retrieval is not exposed in the API.
- It works well enough for most papers.
- Automating metadata retrieval is a separate concern we can address later if
  Zotero's coverage is poor.

### Phase 3 (Deferred): Orphan Re-attachment

Handle Zotero items that exist but have lost their PDF attachment:

1. Query Zotero API for items with no child attachments (or broken attachment
   paths).
2. Try to match each orphaned item to a canonical store file by title or DOI.
3. If a match is found, attach the canonical PDF to the existing Zotero item.

This is lower priority because:
- It is a less common case than new imports.
- It requires fuzzy matching (title similarity), which is harder to get right.
- The existing `findpdfs/bibtex.py` has title-matching code that can be adapted.

## Module Location

`rkb/collection/zotero_sync.py`

### Key Functions

```python
def scan_zotero_hashes(zotero_storage: Path) -> dict[str, Path]:
    """Scan Zotero storage directory.

    Returns a dict mapping SHA-256 hash -> path of the PDF in Zotero storage.
    """

def is_in_zotero(content_sha256: str, zotero_hashes: dict[str, Path]) -> bool:
    """Check if a hash exists in the Zotero hash scan."""

def import_to_zotero(
    canonical_pdf_path: Path,
    display_name: str,
    zot: zotero.Zotero,
) -> tuple[str, str]:
    """Create a Zotero item and attach a PDF.

    Returns (item_key, attachment_key).
    Raises on API failure.
    """

def sync_batch_to_zotero(
    hashes_to_import: list[str],
    catalog: Catalog,
    library_root: Path,
    zot: zotero.Zotero,
    zotero_hashes: dict[str, Path],
) -> dict:
    """Import a batch of canonical files into Zotero.

    Respects Zotero API rate limits.
    Returns summary dict with counts: imported, skipped, failed.
    """
```

## Rate Limiting

The Zotero Web API has rate limits. For bulk imports (during rectification of
2000+ files), we must:
- Batch item creation requests.
- Respect HTTP 429 responses with exponential backoff.
- Log progress so a partial failure can be resumed.

The `sync_batch_to_zotero` function should accept a progress callback for
display purposes.

## Zotero Storage Paths

Zotero stores attachments in:
```
~/Zotero/storage/<8-char-key>/filename.pdf
```

Each attachment has a unique 8-character alphanumeric key. The filename inside
may be the original filename or a Zotero-assigned name. Our hash scan ignores
filenames entirely and hashes the bytes.

On both MacOS and Linux, the default Zotero data directory is `~/Zotero/`.
This is configurable in Zotero's preferences and in our tool via
`PDF_ZOTERO_STORAGE`.

## Verification

1. **Unit test: `scan_zotero_hashes`.** Create a mock directory tree resembling
   Zotero storage (subdirectories with 8-char names, each containing a PDF).
   Verify the returned dict maps correct hashes to correct paths.

2. **Unit test: `import_to_zotero`.** Mock the pyzotero client. Verify that
   `create_items` and `attachment_simple` are called with correct arguments.
   Verify the returned keys.

3. **Integration test: full sync flow.** Create a mock catalog with some files.
   Create a mock Zotero storage with a subset of those files. Run
   `sync_batch_to_zotero`. Verify that only the missing files are imported and
   existing ones are recorded as `pre-existing`.

4. **Rate limit test.** Mock the pyzotero client to return HTTP 429. Verify
   the sync function retries with backoff.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Zotero "Retrieve Metadata" is not programmatic | Accept manual step for now; revisit if coverage is poor |
| pyzotero uses Web API, which syncs to local client with a delay | Do the hash scan before the import batch, not interleaved |
| Rate limiting during bulk import | Batch requests, exponential backoff, progress logging |
| Zotero storage path differs from default | Configurable via `PDF_ZOTERO_STORAGE` env var |
