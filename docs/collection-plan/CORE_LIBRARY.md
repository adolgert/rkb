# Core Library

The core library provides shared functionality used by all commands. It is pure
library code with no CLI, no UI, and no side effects beyond what its callers
request.

## Location

`rkb/collection/` -- a new subpackage within the existing `rkb` package.

### Relationship to existing rkb architecture

The existing `rkb` package has a layered architecture enforced by import-linter:

```
rkb.cli            (top)
rkb.services
rkb.pipelines
rkb.extractors | rkb.embedders
rkb.core           (bottom)
```

The new `rkb.collection` subpackage sits alongside the existing layers. It:
- **May import from** `rkb.core` (for any shared utilities)
- **Must not import from** `rkb.services`, `rkb.pipelines`, `rkb.extractors`,
  `rkb.embedders`
- **Must not be imported by** `rkb.core`
- **May be imported by** `rkb.cli` (for command implementations)

Similarly, `rkb.triage` (the Flask app) may import from `rkb.collection` but
not from the extraction/search layers.

The import-linter configuration in `pyproject.toml` will need new contracts
added to enforce these rules. See the implementation phases document for
details.

## Modules

### `rkb/collection/__init__.py`

Empty or minimal. Marks the subpackage.

### `rkb/collection/hashing.py`

**Responsibility:** Compute SHA-256 of PDF files.

**Key function:**

```python
def hash_file_sha256(path: Path) -> str:
    """Return lowercase hex SHA-256 digest of file contents.

    Uses hashlib.file_digest for memory-efficient streaming hash.
    """
```

**Adapt from:**
- `rkb/core/identity.py` -- already computes SHA-256 (within `DocumentIdentity`)
- `findpdfs/identify.py:file_image_hash()` -- same pattern but uses SHA-1

The new function should be standalone (not wrapped in a class) and use SHA-256
exclusively.

**Verification:**
- Hash a known file and compare against `sha256sum` output.
- Hash the same file twice; confirm identical results.
- Hash two different files; confirm different results.

### `rkb/collection/canonical_store.py`

**Responsibility:** Manage the canonical file store on Dropbox.

**Key functions:**

```python
def canonical_dir(library_root: Path, content_sha256: str) -> Path:
    """Return the directory path for a hash in the canonical store.

    Example: library_root/sha256/ab/cd/abcdef.../
    """

def store_pdf(
    library_root: Path,
    source_path: Path,
    content_sha256: str,
    display_name: str,
) -> Path:
    """Copy a PDF into the canonical store. Return the destination path.

    Creates the directory structure. Copies the file. Verifies integrity
    by re-hashing the destination. Raises on mismatch.

    If the hash directory already exists with a matching PDF, returns the
    existing path without copying (idempotent).
    """

def is_stored(library_root: Path, content_sha256: str) -> bool:
    """Check whether a hash already has a file in the canonical store."""
```

**Adapt from:** `findpdfs/exactmatch.py:decide_destination_path()` for the
hash-prefix directory idea, but with the new layout (2-level prefix + full hash
directory + human-readable filename).

**Verification:**
- Store a file, verify it exists at the expected path.
- Re-hash the stored copy; confirm it matches the original.
- Store the same file again; confirm no error and no duplicate.
- Attempt to store with a wrong hash; confirm it raises.

### `rkb/collection/display_name.py`

**Responsibility:** Generate human-readable filenames from PDF content or
metadata.

**Key function:**

```python
def generate_display_name(
    pdf_path: Path,
    metadata: dict | None = None,
) -> str:
    """Generate a sanitized display filename for a PDF.

    Priority:
      1. metadata dict (keys: 'author', 'year', 'title') if provided
      2. First-page text parse (quick heuristic for author/title)
      3. Original filename

    Returns a sanitized string ending in .pdf, max 120 characters.
    """
```

The first-page parse is a best-effort heuristic. It does not need to be
perfect -- the original filename is an acceptable fallback, and the display
name can always be corrected later without affecting the system.

**Adapt from:** `findpdfs/gather.py:pdf_text()` for first-page text
extraction.

**Verification:**
- Known metadata dict produces expected name.
- PDF with extractable first page produces reasonable name.
- PDF with no extractable text falls back to original filename.
- Unicode and special characters are sanitized.
- Very long titles are truncated.

### `rkb/collection/catalog.py`

**Responsibility:** All SQLite operations on `pdf_catalog.db`.

**Key class:**

```python
class Catalog:
    def __init__(self, db_path: Path): ...
    def initialize(self) -> None: ...

    # Canonical files
    def add_canonical_file(
        self, content_sha256, canonical_path, display_name,
        original_filename, page_count, file_size_bytes,
    ) -> None: ...
    def is_known(self, content_sha256: str) -> bool: ...
    def get_canonical_file(self, content_sha256: str) -> dict | None: ...

    # Source sightings
    def add_source_sighting(
        self, content_sha256, source_path, machine_id,
    ) -> None: ...

    # Zotero links
    def set_zotero_link(
        self, content_sha256, zotero_item_key, status,
    ) -> None: ...
    def get_unlinked_to_zotero(self) -> list[str]: ...

    # Logging
    def log_action(
        self, content_sha256, action, source_path, detail,
    ) -> None: ...

    # Reporting
    def get_statistics(self) -> dict: ...
```

`initialize()` creates all tables if they do not exist (using `CREATE TABLE IF
NOT EXISTS`). This makes the catalog safe to open on a fresh database or an
existing one.

**Verification:**
- Create a catalog in-memory (`:memory:`), initialize, add a file, query it.
- Add duplicate hash; confirm it raises or is silently idempotent.
- `get_statistics()` returns correct counts after a series of operations.
- `get_unlinked_to_zotero()` returns files that are in canonical_files but have
  no zotero_links entry or have `status='failed'`.

### `rkb/collection/config.py`

**Responsibility:** Load configuration from environment variables, config file,
and defaults. Provide a single `CollectionConfig` object that other modules use.

**Key class:**

```python
@dataclass
class CollectionConfig:
    library_root: Path
    catalog_db: Path
    zotero_storage: Path
    box_staging: Path
    work_downloads: Path
    machine_id: str
    zotero_library_id: str | None
    zotero_api_key: str | None
    zotero_library_type: str

    @classmethod
    def load(cls) -> "CollectionConfig": ...
```

**Verification:**
- Defaults are reasonable on both MacOS and Linux.
- Environment variables override defaults.
- Missing optional values (Zotero credentials) result in `None`, not errors.

## What This Module Does NOT Do

- No CLI commands (those live in `rkb/cli/commands/`)
- No Zotero API calls (those live in `rkb/collection/zotero_sync.py`, a
  separate module built in a later phase)
- No Flask/UI code (that lives in `rkb/triage/`)
- No PDF page rendering
