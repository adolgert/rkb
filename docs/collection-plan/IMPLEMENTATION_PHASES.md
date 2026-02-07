# Implementation Phases

## Overview

The implementation is organized into phases with explicit dependencies. Within
each phase, independent work items can proceed in parallel. Each phase has
clear entry criteria, exit criteria, and verification steps.

## Dependency Graph

```
Phase 1: Core Library
    |-- hashing.py            -+
    |-- canonical_store.py     |  (all independent, can build in parallel)
    |-- display_name.py        |
    |-- catalog.py             |
    +-- config.py             -+
         |
         v
Phase 2a: Home Ingest        Phase 2b: Zotero Module     Phase 2c: Work Triage
(no Zotero)                   (sync logic)                (Flask app)
    |                              |                           |
    |   needs core library         |  needs hashing + catalog  |  needs hashing only
    |                              |                           |
    +----------+-------------------+                           |
               |                                               |
               v                                               |
Phase 3: Integration                                           |
(ingest + Zotero + rectify)                                    |
    |                                                          |
    +---------<-- can merge triage if done ----<---------------+
    |
    v
Phase 4: Status + Polish
```

**Key parallelization opportunities:**

After Phase 1 completes, **three independent workstreams** can proceed
simultaneously:
- **Agent A:** Phase 2a (Home Ingest without Zotero)
- **Agent B:** Phase 2b (Zotero Sync Module)
- **Agent C:** Phase 2c (Work Triage App)

Phase 3 begins when Phases 2a and 2b are both done. Phase 2c (triage) has no
dependency on 2a or 2b and can proceed independently; it only needs Phase 1's
hashing module.

---

## Phase 1: Core Library

**Goal:** Build the shared foundation that all commands depend on.

**What to build:**

| Module | Responsibility | Key reference |
|--------|---------------|---------------|
| `rkb/collection/__init__.py` | Subpackage marker | -- |
| `rkb/collection/hashing.py` | SHA-256 file hashing | `rkb/core/identity.py`, `findpdfs/identify.py` |
| `rkb/collection/canonical_store.py` | Store layout, copy with integrity verification | `findpdfs/exactmatch.py` |
| `rkb/collection/display_name.py` | Human-readable filename generation | `findpdfs/gather.py` |
| `rkb/collection/catalog.py` | SQLite catalog (all table creation and CRUD) | DATA_MODEL.md |
| `rkb/collection/config.py` | Configuration loading | DATA_MODEL.md configuration section |

**Parallelization:** All five modules are independent of each other. Each
module and its test file can be built by a separate agent. The only shared
input is the DATA_MODEL.md spec for schemas and paths.

**What the implementing agent needs to know:**
- DATA_MODEL.md for schema definitions and path layout.
- CORE_LIBRARY.md for module responsibilities and function signatures.
- The existing code in `rkb/core/identity.py` and `findpdfs/identify.py` (for
  reference, not to import from).
- The rkb package's import-linter rules in `pyproject.toml`. New modules must
  satisfy the existing contracts. The new `rkb.collection` subpackage must not
  import from `rkb.services`, `rkb.pipelines`, `rkb.extractors`, or
  `rkb.embedders`. It may import from `rkb.core`.

**Import-linter update required:** Add contracts to `pyproject.toml` ensuring
`rkb.collection` respects the architecture. This can be a sub-task within
Phase 1 or done as preparation before the module work begins:

```toml
# Collection layer: can import from core, nothing else internal
[[tool.importlinter.contracts]]
name = "Collection layer isolation"
type = "forbidden"
source_modules = ["rkb.collection"]
forbidden_modules = [
    "rkb.services",
    "rkb.pipelines",
    "rkb.extractors",
    "rkb.embedders",
    "rkb.cli",
]
```

**Exit criteria:**
- All modules have unit tests that pass.
- `pytest` passes.
- `ruff check` passes.
- `lint-imports` passes (including new contracts).
- A test can: create a catalog in memory, add a file, query it, get correct
  results.
- A test can: generate a canonical path and verify its directory structure.
- A test can: hash a file and get a stable, correct SHA-256 result.
- A test can: generate a display name from a PDF with known content.

---

## Phase 2a: Home Ingest (without Zotero)

**Goal:** Build the `rkb ingest` command that copies PDFs to the canonical
store, without Zotero integration (using `--skip-zotero` as default behavior).

**What to build:**

| Module | Responsibility |
|--------|---------------|
| `rkb/collection/scanner.py` | Discover `.pdf` files in directories recursively |
| `rkb/collection/ingest.py` | Orchestrate the ingest flow (hash, dedup, copy, record) |
| `rkb/cli/commands/ingest_cmd.py` | CLI argument parsing and command wiring |
| Update `rkb/cli/main.py` | Register `ingest` subcommand |

**Depends on:** Phase 1 (core library).

**Does NOT depend on:** Zotero module. The `--skip-zotero` flag omits the
Zotero step entirely. The Zotero integration is wired in during Phase 3.

**What the implementing agent needs to know:**
- HOME_INGEST.md for the complete command spec and processing flow.
- The core library API (from Phase 1): `Catalog`, `store_pdf`,
  `hash_file_sha256`, `generate_display_name`, `CollectionConfig`.
- The existing rkb CLI structure: `rkb/cli/main.py` uses `argparse` with
  subparsers. Commands are in `rkb/cli/commands/`. Each command module
  exports `add_arguments(parser)` and `execute(args)`.

**Exit criteria:**
- `rkb ingest ~/some/test/directory` works end-to-end on a test directory.
- Canonical store has correct directory structure with human-readable filenames.
- Catalog database has correct records in `canonical_files` and
  `source_sightings`.
- Running ingest twice on the same directory: second run reports all as
  duplicates, no new files copied.
- `--dry-run` reports correctly without side effects.
- Unreadable files are reported as failures without blocking other files.
- All tests pass (`pytest`, `ruff check`, `lint-imports`).

---

## Phase 2b: Zotero Sync Module

**Goal:** Build the Zotero integration module that can scan Zotero storage for
existing PDFs and import new ones via the pyzotero API.

**What to build:**

| Module | Responsibility |
|--------|---------------|
| `rkb/collection/zotero_sync.py` | Hash scanning, pyzotero import, batch sync with rate limiting |

**Depends on:** Phase 1 (hashing module and catalog).

**Can happen in parallel with:** Phase 2a and Phase 2c.

**What the implementing agent needs to know:**
- ZOTERO_INTEGRATION.md for the complete spec.
- pyzotero API documentation: https://pyzotero.readthedocs.io/
- The hashing and catalog APIs from Phase 1.
- Zotero storage directory structure: `~/Zotero/storage/<8-char-key>/file.pdf`.

**pyzotero dependency:** Add `pyzotero>=1.6.0` to `[project.optional-dependencies]`
in `pyproject.toml` under a new `[zotero]` extra:

```toml
zotero = ["pyzotero>=1.6.0"]
```

**Exit criteria:**
- `scan_zotero_hashes(path)` correctly scans a mock Zotero storage tree.
- `import_to_zotero(path, name, zot)` calls pyzotero correctly (mocked).
- `sync_batch_to_zotero(...)` imports only files not already in Zotero.
- Rate limiting: mock 429 responses, verify backoff and retry.
- All tests pass.

---

## Phase 2c: Work Triage App

**Goal:** Build the Flask-based PDF review application for the work machine.

**What to build:**

| Module | Responsibility |
|--------|---------------|
| `rkb/triage/__init__.py` | Subpackage marker |
| `rkb/triage/app.py` | Flask application factory and routes |
| `rkb/triage/decisions.py` | Triage database CRUD (triage.db) |
| `rkb/triage/pdf_renderer.py` | PyMuPDF page-to-PNG rendering |
| `rkb/triage/staging.py` | Staging directory management (copy on approve, delete on reject, rebuild) |
| `rkb/triage/templates/*.html` | HTML templates (review page, queue, history) |
| `rkb/triage/static/` | CSS and minimal JS |
| `rkb/cli/commands/triage_cmd.py` | CLI entry point to launch the app |
| Update `rkb/cli/main.py` | Register `triage` subcommand |

**Depends on:** Phase 1 (hashing module only). The triage app uses its own
database (`triage.db`) and does not interact with the catalog, canonical store,
Zotero, or any home-side module.

**Can happen in parallel with:** Phase 2a and Phase 2b.

**What the implementing agent needs to know:**
- WORK_TRIAGE.md for the complete spec.
- The hashing module API from Phase 1 (`hash_file_sha256`).
- The triage database schema from DATA_MODEL.md.
- PyMuPDF's page rendering: `doc = fitz.open(path); pix = doc[0].get_pixmap(); pix.tobytes("png")`.
- Flask basics: routes, templates, `url_for`, `request.form`.

**Import-linter update:** Add a contract for the triage subpackage:

```toml
[[tool.importlinter.contracts]]
name = "Triage layer isolation"
type = "forbidden"
source_modules = ["rkb.triage"]
forbidden_modules = [
    "rkb.services",
    "rkb.pipelines",
    "rkb.extractors",
    "rkb.embedders",
]
```

**New dependencies:** Add Flask and PyMuPDF to `pyproject.toml` under a
`[triage]` optional dependency group:

```toml
triage = [
    "flask>=3.0.0",
    "pymupdf>=1.23.0",
]
```

**Exit criteria:**
- Web app launches and displays PDFs from a test directory.
- Can approve, reject, and change decisions via the UI.
- Approving copies the file to the staging directory.
- Rejecting a previously-approved file removes it from staging.
- Decision history is recorded.
- `--rebuild-staging` reconstructs the staging directory from the database.
- Filter tabs (all/undecided/approved/rejected) work.
- Previously-decided files show their old decision when re-scanned.
- All tests pass (`pytest`, `ruff check`, `lint-imports`).

---

## Phase 3: Integration (Ingest + Zotero + Rectify)

**Goal:** Wire Zotero into the ingest flow and build the rectification command.

**What to build:**

| Module | Responsibility |
|--------|---------------|
| Update `rkb/collection/ingest.py` | Add Zotero import step (enabled by default, `--skip-zotero` to disable) |
| `rkb/collection/rectify.py` | Rectification logic: full scan, bidirectional gap analysis, batch processing |
| `rkb/cli/commands/rectify_cmd.py` | CLI command for rectification |
| Update `rkb/cli/main.py` | Register `rectify` subcommand |

**Depends on:** Phases 2a and 2b both complete.

**What the implementing agent needs to know:**
- RECTIFY.md for the rectification spec.
- HOME_INGEST.md for the Zotero-enabled ingest flow.
- The ingest module API from Phase 2a.
- The zotero_sync module API from Phase 2b.

**Exit criteria:**
- `rkb ingest` with Zotero enabled: imports new files to both store and
  Zotero, skips files already in both.
- `rkb rectify --report` produces accurate gap analysis across multiple
  directories.
- `rkb rectify` fills all gaps (canonical store + Zotero).
- `rkb rectify` handles the reverse case: files in Zotero but not in the
  canonical store.
- Running rectify twice: second run shows zero actions needed.
- All tests pass.

---

## Phase 4: Status and Polish

**Goal:** Status reporting command and operational polish.

**What to build:**

| Module | Responsibility |
|--------|---------------|
| `rkb/cli/commands/status_cmd.py` | `rkb status` command: canonical store size, Zotero link coverage, recent ingest activity |
| Update `rkb/cli/main.py` | Register `status` subcommand |
| Progress bars | Add tqdm progress bars to ingest and rectify for large batches |
| Edge case handling | Permission errors, disk full, empty directories, zero-byte PDFs |

**Depends on:** Phase 3.

**Exit criteria:**
- `rkb status` shows accurate counts: total canonical files, Zotero-linked
  files, unlinked files, recent ingest log entries.
- `rkb status --json` produces machine-readable output.
- Ingest and rectify show progress bars for batches > 10 files.
- All commands handle edge cases without crashing.
- All tests pass.

---

## Summary: Parallelization Map

```
PHASE 1: Core Library (foundation -- must complete first)
  Work items (all parallel):
    [1a] hashing.py + tests
    [1b] canonical_store.py + tests
    [1c] display_name.py + tests
    [1d] catalog.py + tests
    [1e] config.py + tests
    [1f] import-linter contract updates

         |
         | Phase 1 complete
         |
    +----+----+----+
    |         |    |
    v         v    v

PHASE 2a     2b   2c
Ingest    Zotero  Triage
(Agent A) (B)     (Agent C)
    |         |        |
    +----+----+        |
         |             |
         v             |
PHASE 3               |
Integration      (merges when done)
         |             |
         +------+------+
                |
                v
         PHASE 4
         Status + Polish
```

**Minimum calendar path:** Phases 1 -> (2a + 2b in parallel) -> 3 -> 4.
Phase 2c (triage) is on a separate track and can be done anytime after Phase 1.

## Testing Strategy Across Phases

Every phase must pass these checks before it is considered done:
- `pytest` -- all tests pass (including tests from prior phases).
- `ruff check` -- no lint violations.
- `lint-imports` -- no import-linter violations.

Tests should use temporary directories and in-memory SQLite databases wherever
possible. No test should require network access, a running Zotero instance, or
real PDF files (use small synthetic PDFs generated in test fixtures).

For the triage app, Flask's test client (`app.test_client()`) enables testing
HTTP routes without launching a real server.
