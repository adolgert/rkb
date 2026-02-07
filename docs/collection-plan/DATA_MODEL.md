# Data Model

## Canonical Store Layout

Root: `~/Dropbox/findpdfs-library/` (configurable via `PDF_LIBRARY_ROOT`
environment variable).

```
$PDF_LIBRARY_ROOT/
  sha256/
    ab/
      cd/
        abcdef0123456789...full_hash/
          Smith 2024 Bayesian survival analysis.pdf
  db/
    pdf_catalog.db
```

### Path derivation

Given a PDF with SHA-256 hash `abcdef0123456789...`:

1. Take first 2 hex characters -> directory level 1: `ab/`
2. Take next 2 hex characters -> directory level 2: `cd/`
3. Full 64-character hash -> directory level 3: `abcdef0123456789.../`
4. Human-readable filename inside that directory

The two-level prefix limits any single directory to at most 256 subdirectories.
Each hash directory contains exactly one PDF.

### Display name generation

Priority order for constructing the human-readable filename:

1. **Metadata available** (from BibTeX, Zotero, or first-page parse): use
   `LastName Year Title fragment.pdf`, e.g., `Smith 2024 Bayesian survival analysis.pdf`
2. **No metadata**: use the original filename as-is, e.g., `2401.12345v2.pdf`
3. **Last resort** (no metadata, no original filename): `abcdef01.pdf` (hash prefix)

Sanitization rules:
- Replace characters not in `[a-zA-Z0-9 ._-]` with spaces
- Collapse multiple consecutive spaces to one
- Strip leading/trailing whitespace
- Cap total filename length at 120 characters (including `.pdf`)
- Ensure filename ends with `.pdf`

### Immutability rules

- Files under `sha256/` are immutable once written. The tool never overwrites
  or deletes files in the canonical store.
- Each hash directory contains exactly one PDF.
- The display name is a convenience for humans. The hash directory is the
  identity. If the display name is wrong, renaming it changes nothing about the
  system's behavior.

## Home Database: `pdf_catalog.db`

Location: `$PDF_LIBRARY_ROOT/db/pdf_catalog.db`

This is a fresh SQLite database. It does not inherit schema or data from the
existing `rkb_documents.db`. If we later need to cross-reference old extraction
records (when adding Markdown conversion), we can join against the old database
using `content_sha256` as the key.

### Table: `canonical_files`

The registry of every unique PDF in the canonical store.

```sql
CREATE TABLE canonical_files (
    content_sha256 TEXT PRIMARY KEY,
    canonical_path TEXT NOT NULL,
    display_name TEXT NOT NULL,
    original_filename TEXT,
    page_count INTEGER,
    file_size_bytes INTEGER,
    ingested_at TEXT NOT NULL           -- ISO 8601 UTC
);
```

### Table: `source_sightings`

Every place we have ever seen a given PDF. Provides provenance tracking and
helps answer "where did this paper come from?"

```sql
CREATE TABLE source_sightings (
    content_sha256 TEXT NOT NULL
        REFERENCES canonical_files(content_sha256),
    source_path TEXT NOT NULL,
    machine_id TEXT NOT NULL,           -- e.g. "work-macbook", "home-popos"
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (content_sha256, source_path, machine_id)
);

CREATE INDEX idx_sightings_hash ON source_sightings(content_sha256);
```

### Table: `zotero_links`

Tracks which canonical PDFs have been imported into Zotero and their status.

```sql
CREATE TABLE zotero_links (
    content_sha256 TEXT PRIMARY KEY
        REFERENCES canonical_files(content_sha256),
    zotero_item_key TEXT,
    zotero_attachment_key TEXT,
    status TEXT NOT NULL
        CHECK(status IN ('imported', 'pre-existing', 'failed', 'pending')),
    error_message TEXT,
    linked_at TEXT NOT NULL
);
```

### Table: `ingest_log`

Append-only log of every ingest action. Useful for debugging and auditing.

```sql
CREATE TABLE ingest_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_sha256 TEXT NOT NULL,
    action TEXT NOT NULL,               -- 'ingested', 'skipped_duplicate',
                                        -- 'zotero_imported', 'zotero_skipped',
                                        -- 'failed'
    source_path TEXT,
    detail TEXT,                         -- human-readable note or error message
    timestamp TEXT NOT NULL
);
```

## Work-Side Database: `triage.db`

Location: `~/Documents/box-staging/triage.db`

This database lives only on the work machine. It is never synced home. The home
machine does not know or care about triage decisions.

### Table: `triage_decisions`

```sql
CREATE TABLE triage_decisions (
    content_sha256 TEXT PRIMARY KEY,
    decision TEXT NOT NULL
        CHECK(decision IN ('approved', 'rejected')),
    original_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size_bytes INTEGER,
    page_count INTEGER,
    decided_at TEXT NOT NULL,
    staged_path TEXT                     -- path in staging dir; NULL if rejected
);
```

### Table: `decision_history`

Enables auditing of changed decisions. Every change (including the initial
decision) appends a row.

```sql
CREATE TABLE decision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_sha256 TEXT NOT NULL,
    old_decision TEXT,                   -- NULL for first decision
    new_decision TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
```

## Configuration

All paths are configurable. Defaults are sensible for the owner's setup.

| Setting | Default | Env var |
|---------|---------|---------|
| Library root | `~/Dropbox/findpdfs-library` | `PDF_LIBRARY_ROOT` |
| Catalog database | `$PDF_LIBRARY_ROOT/db/pdf_catalog.db` | `PDF_CATALOG_DB` |
| Zotero storage | `~/Zotero/storage` | `PDF_ZOTERO_STORAGE` |
| Box staging (work) | `~/Documents/box-staging` | `PDF_BOX_STAGING` |
| Work downloads | `~/Downloads` | `PDF_WORK_DOWNLOADS` |
| Machine ID | `(hostname)` | `PDF_MACHINE_ID` |

A YAML config file at `$PDF_LIBRARY_ROOT/config.yaml` (or
`~/.config/rkb/collection.yaml`) may also be used. Environment variables
override the config file, which overrides defaults.

### Zotero API credentials

Required for Zotero import (not for hash scanning of local Zotero storage):

| Setting | Env var |
|---------|---------|
| Zotero user library ID | `ZOTERO_LIBRARY_ID` |
| Zotero API key | `ZOTERO_API_KEY` |
| Zotero library type | `ZOTERO_LIBRARY_TYPE` (default: `user`) |

These should be stored in environment variables or a dotenv file, never in
source code or committed config files.
