# Work Triage: `rkb triage`

## Purpose

A local web application for reviewing PDFs on the work machine. The user sees
PDFs from `~/Downloads` sorted by date, views pages 1-2, and marks each with a
thumbs-up or thumbs-down decision. Decisions are mutable -- any decision can be
reversed at any time. Approved files are staged in `~/Documents/box-staging/`
for manual upload to Box.

## Command Interface

```bash
rkb triage                              # Launch on default port (5000)
rkb triage --port 8080                  # Custom port
rkb triage --downloads ~/Downloads      # Custom source directory
rkb triage --rebuild-staging            # Reconstruct staging dir from decisions
```

## Design Principle: Forward and Backward

The most important property of the triage system is that decisions are
reversible. If you can approve a file, you can un-approve it. If you can reject
a file, you can un-reject it. The staging directory always reflects the current
set of approvals, not the historical sequence of decisions.

This means:
- Approving a file copies it to staging.
- Rejecting a previously-approved file removes it from staging.
- The staging directory is always derivable from the database.
  `--rebuild-staging` can reconstruct it from scratch.
- The `decision_history` table records every change for auditability, but only
  the current decision in `triage_decisions` determines system behavior.

## Application Architecture

**Backend:** Flask (Python)
**Frontend:** Server-rendered HTML with minimal JavaScript (no framework needed)
**PDF rendering:** PyMuPDF renders PDF pages to PNG images
**Database:** SQLite `triage.db` in `~/Documents/box-staging/`
**Platform:** MacOS (work laptop)

### Module location

```
rkb/triage/
    __init__.py
    app.py              # Flask application factory
    decisions.py        # Database operations (triage.db CRUD)
    pdf_renderer.py     # PyMuPDF page-to-image rendering
    staging.py          # Staging directory management
    templates/
        layout.html     # Base template
        review.html     # Main review page
        queue.html      # Approved/staged files view
        history.html    # Decision history view
    static/
        style.css       # Minimal styling
        triage.js       # Button handlers, AJAX decision submission
```

### Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Main review page: paginated list of PDFs, newest first |
| `/pdf/<hash>/pages` | GET | Page 1-2 images for a specific PDF |
| `/pdf/<hash>/decide` | POST | Record or change a decision |
| `/queue` | GET | Approved files not yet transferred |
| `/history` | GET | Browse all past decisions with filters |
| `/api/stats` | GET | JSON counts: undecided, approved, rejected, transferred |

## Main Review Page

Shows a card for each PDF found in the source directory:

- Original filename
- File size, page count
- Date modified (from filesystem mtime)
- Thumbnail of page 1 (expandable to see page 2)
- Current decision status displayed visually:
  - **Undecided** (neutral/gray)
  - **Approved** (green)
  - **Rejected** (red)
- Two buttons: thumbs-up (approve) and thumbs-down (reject)
- Filter tabs: **All** | **Undecided** | **Approved** | **Rejected**

Default sort: newest files first (by filesystem modification time).

Changing a decision is the same gesture as making one: click the opposite
button. There is no separate "undo" action.

## Decision Flow

### Approve (or change to approved)

1. User clicks thumbs-up on a PDF.
2. POST to `/pdf/<hash>/decide` with `decision=approved`.
3. Backend:
   - Upsert `triage_decisions`: set `decision='approved'`, update
     `decided_at`, set `staged_path`.
   - Append to `decision_history` (recording `old_decision` if one existed).
   - Copy the PDF to `~/Documents/box-staging/<filename>`.
   - If a filename collision exists in staging (different hash, same name),
     append a hash prefix: `paper_abcdef01.pdf`.
4. UI updates the card to show approved (green).

### Reject (or change to rejected)

1. User clicks thumbs-down.
2. POST to `/pdf/<hash>/decide` with `decision=rejected`.
3. Backend:
   - Upsert `triage_decisions`: set `decision='rejected'`, clear `staged_path`.
   - Append to `decision_history`.
   - **If the file was previously approved and exists in staging, delete it
     from the staging directory.**
4. UI updates the card to show rejected (red).

### Transfer workflow

When the user is ready to upload to Box:

1. View the queue page (`/queue`) or run `rkb triage --queue` in the terminal.
   This shows all currently-approved files in the staging directory.
2. The user manually uploads `~/Documents/box-staging/*.pdf` to Box (via
   browser or Box Drive if available).
3. The user may optionally mark files as transferred. This is a convenience for
   tracking, not a system requirement. Transferred files remain in the database
   with their decision intact.

## Scanning Logic

On startup and on page refresh:

1. Scan `~/Downloads/*.pdf` (non-recursive by default; configurable).
2. For each PDF found, compute SHA-256.
3. Look up hash in `triage_decisions`:
   - Known hash with existing decision: show with that decision.
   - Unknown hash: show as undecided.
4. Files that have been removed from Downloads but have a decision in the
   database still appear in the history view but not in the main review page.
   Their decisions are preserved -- if the same file appears again later, the
   old decision is remembered.

## Staging Directory Integrity

The staging directory (`~/Documents/box-staging/`) should always contain
exactly the set of PDFs that are currently approved and not yet confirmed as
transferred.

`rkb triage --rebuild-staging` reconstructs this by:
1. Clearing all PDFs from the staging directory (but not `triage.db`).
2. For each `triage_decisions` row with `decision='approved'`:
   - If the source file still exists at `original_path`, copy it to staging.
   - If the source file is gone, log a warning (the approval stands but
     the file cannot be staged).

## Dependencies

- Core library: `rkb.collection.hashing` (SHA-256 only)
- Flask
- PyMuPDF (for page rendering)
- Does NOT depend on: catalog, canonical_store, Zotero, or any home-side module

## Platform Notes

- The work machine is MacOS.
- PyMuPDF and Flask both install cleanly on MacOS via pip.
- The Flask app runs on localhost only. No external network access is needed.
- The triage database and staging directory are local to the work machine.
  They are never synced to Dropbox or any shared filesystem.

## Verification

1. **Unit tests: decisions module.** Record a decision, change it, verify the
   database state. Verify `decision_history` captures changes.

2. **Unit tests: staging module.** Approve a file, verify it appears in staging.
   Reject a previously-approved file, verify it is removed from staging.
   Rebuild staging from database, verify consistency.

3. **Flask test client.** Simulate the full approve/reject/change flow via HTTP
   requests. Verify database state and staging directory state after each
   action.

4. **Filename collision test.** Approve two different PDFs that have the same
   original filename. Verify both appear in staging with disambiguated names.

5. **Scan with remembered decisions.** Place a PDF in Downloads, approve it,
   remove it from Downloads, re-add it. Verify the old decision is shown.

6. **Manual test.** Launch the app with a directory of sample PDFs. Exercise
   the full UI: browse, approve, reject, change mind, view queue, view history.
