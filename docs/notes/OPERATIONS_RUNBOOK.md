# Operations Runbook (Daily Use)

This runbook is for predictable operation when context is limited.

## Golden Rules

1. Canonical PDF store is authority.
2. `content_sha256` is the only identity for dedup.
3. Rerunning commands is allowed and expected.

## Daily Routine (Any Machine)

```bash
pdf sync
```

What this does:
- Finds new PDFs in configured roots.
- Ingests only unseen content into canonical store.

## Work Machine -> Home Transfer

On work machine:

```bash
pdf sync
pdf export --to ~/Box/findpdfs-outbox/work-YYYY-MM-DD.zip
```

On home machine:

```bash
pdf import ~/Box/findpdfs-outbox/work-YYYY-MM-DD.zip
```

## Home Desktop Nightly

```bash
pdf convert --only-new
pdf index --only-new
```

## Weekly Maintenance

```bash
pdf status
pdf link-zotero --mode copy --only-unlinked
```

Interpretation:
- If canonical-not-converted > 0, run `pdf convert --only-new`.
- If converted-not-indexed > 0, run `pdf index --only-new`.
- If failures exist, run retry workflow below.

## Retry Workflow

Conversion failures:

```bash
pdf convert --retry-failed
```

Index failures:

```bash
pdf index --retry-failed
```

If repeated failures continue:
1. Capture `pdf status --json` output.
2. Inspect top failure reasons.
3. Fix dependency/config issue.
4. Rerun retry command.

## Incident Playbooks

### A) Interrupted sync/export/import

Action:
- Rerun same command.

Reason:
- Commands are required to be idempotent.

### B) Hash mismatch on import

Action:
1. Quarantine mismatched file.
2. Re-export from source machine.
3. Re-import package.

Never:
- Force ingest a mismatched file.

### C) Missing canonical file reported

Action:
1. Locate alternate source path in `document_sources`.
2. Rebuild canonical file from source.
3. Re-run `pdf status`.

### D) Zotero link mismatch

Action:
1. Keep canonical store untouched.
2. Re-run `pdf link-zotero --only-unlinked`.
3. If needed, relink specific `content_sha256` manually.

## Operator Shortcuts

When busy, remember only these:

1. `pdf sync`
2. `pdf status`
3. On home: `pdf convert --only-new && pdf index --only-new`

## What Not To Do

- Do not use Zotero attachment path as canonical source.
- Do not dedup by filename.
- Do not use MD5/SHA-1 identity for new workflow.
- Do not delete legacy stores until migration checklist is complete.
