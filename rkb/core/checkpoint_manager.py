"""Checkpoint management for resumable processing operations."""

import json
from datetime import datetime
from pathlib import Path


class CheckpointManager:
    """Manages processing checkpoints for resumability.

    Enables long-running extraction jobs to be interrupted and resumed
    by tracking completed files in checkpoint files.
    """

    def __init__(self, checkpoint_dir: Path):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoint files
        """
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        batch_id: str,
        completed_files: list[str],
        metadata: dict | None = None,
    ) -> None:
        """Save progress checkpoint.

        Args:
            batch_id: Unique identifier for this batch
            completed_files: List of file paths that have been processed
            metadata: Optional metadata about the batch
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}.json"
        checkpoint_data = {
            "batch_id": batch_id,
            "completed_files": completed_files,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        checkpoint_file.write_text(json.dumps(checkpoint_data, indent=2))

    def load_checkpoint(self, batch_id: str) -> dict | None:
        """Load existing checkpoint.

        Args:
            batch_id: Unique identifier for the batch

        Returns:
            Checkpoint data if exists, None otherwise
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}.json"
        if not checkpoint_file.exists():
            return None
        return json.loads(checkpoint_file.read_text())

    def clear_checkpoint(self, batch_id: str) -> None:
        """Remove checkpoint after successful completion.

        Args:
            batch_id: Unique identifier for the batch
        """
        checkpoint_file = self.checkpoint_dir / f"{batch_id}.json"
        checkpoint_file.unlink(missing_ok=True)

    def get_remaining_files(
        self, batch_id: str, all_files: list[Path]
    ) -> list[Path]:
        """Get files that still need processing.

        Args:
            batch_id: Unique identifier for the batch
            all_files: Complete list of files to process

        Returns:
            List of files not yet completed
        """
        checkpoint = self.load_checkpoint(batch_id)
        if not checkpoint:
            return all_files

        completed = set(checkpoint["completed_files"])
        return [f for f in all_files if str(f) not in completed]
