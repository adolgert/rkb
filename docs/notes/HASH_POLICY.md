# Hash Policy

This policy removes hash ambiguity across the system.

## Authoritative Hash

- Authoritative identity hash: `SHA-256` of canonical PDF bytes.
- Field name: `content_sha256`.
- Format: lowercase hex string.

## Allowed Uses by Hash Type

### SHA-256

Allowed for:
- Document identity
- Deduplication
- Transfer manifest IDs
- Canonical storage path derivation
- Conversion/index keying

### SHA-1

Allowed only for:
- Legacy migration lookup from older systems
- Temporary compatibility reports

Not allowed for:
- New identity or dedup decisions

### MD5

Allowed only for:
- Non-identity cache keys where collision risk is acceptable
- Explicitly labeled legacy metadata

Not allowed for:
- Document identity
- Deduplication
- Integrity checks in transfer pipeline

## Code-Level Policy

Required actions:
1. Ensure all ingest/dedup paths call SHA-256 hashing.
2. Rename or isolate MD5 helpers so they cannot be mistaken for identity hashing.
3. Add lint/test checks that fail if dedup code references MD5/SHA-1 helpers.

Current known risk in `kbase`:
- `rkb/core/text_processing.py:hash_file()` currently computes MD5.

Policy fix:
- Introduce explicit helpers:
  - `hash_file_sha256(path)`
  - `hash_file_md5_legacy(path)`
- Update callers so dedup/identity paths only use SHA-256 helper.

## Database Policy

- `documents.content_sha256` required for all new docs.
- Unique constraint on `content_sha256` after migration backfill.
- Optional legacy columns may retain SHA-1/MD5 for audit only.

## Transfer Integrity Policy

On import:
1. Compute SHA-256 from transferred file bytes.
2. Compare to manifest `content_sha256`.
3. Reject and quarantine on mismatch.

## Audit Requirements

`pdf status` must report:
- Records missing `content_sha256`.
- Duplicate `content_sha256` rows (if any before uniqueness enforced).
- Any pipeline stage still using SHA-1/MD5 for identity.

## Transition Timeline

1. Phase 1: Add SHA-256 fields and backfill.
2. Phase 2: Route all new ingest to SHA-256.
3. Phase 3: Enforce uniqueness and block non-SHA-256 identity paths.
4. Phase 4: Keep SHA-1/MD5 only in legacy migration reports.
