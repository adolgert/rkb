"""File hashing helpers for collection management."""

from hashlib import file_digest
from pathlib import Path


def hash_file_sha256(path: Path) -> str:
    """Return lowercase SHA-256 hex digest for file contents."""
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError(f"Expected a file path, got: {path}")

    with path.open("rb") as input_file:
        return file_digest(input_file, "sha256").hexdigest()

