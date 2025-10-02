"""Tests for CheckpointManager."""

import json
import tempfile
from pathlib import Path

import pytest

from rkb.core.checkpoint_manager import CheckpointManager


class TestCheckpointManagerBasics:
    """Test basic checkpoint operations."""

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def checkpoint_manager(self, temp_checkpoint_dir):
        """Create CheckpointManager instance."""
        return CheckpointManager(temp_checkpoint_dir)

    def test_create_checkpoint_directory(self, temp_checkpoint_dir):
        """Test checkpoint directory is created."""
        # Use subdirectory that doesn't exist yet
        checkpoint_dir = temp_checkpoint_dir / "checkpoints"
        assert not checkpoint_dir.exists()

        manager = CheckpointManager(checkpoint_dir)

        assert checkpoint_dir.exists()
        assert checkpoint_dir.is_dir()
        assert manager.checkpoint_dir == checkpoint_dir

    def test_save_checkpoint_creates_file(self, checkpoint_manager, temp_checkpoint_dir):
        """Test save_checkpoint creates JSON file."""
        batch_id = "test_batch_123"
        completed_files = ["/path/to/file1.pdf", "/path/to/file2.pdf"]
        metadata = {"total": 10}

        checkpoint_manager.save_checkpoint(batch_id, completed_files, metadata)

        checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"
        assert checkpoint_file.exists()
        assert checkpoint_file.is_file()

    def test_save_checkpoint_content(self, checkpoint_manager, temp_checkpoint_dir):
        """Test save_checkpoint writes correct JSON structure."""
        batch_id = "test_batch_456"
        completed_files = ["/path/to/file1.pdf", "/path/to/file2.pdf"]
        metadata = {"total": 10, "extractor": "nougat"}

        checkpoint_manager.save_checkpoint(batch_id, completed_files, metadata)

        checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"
        with checkpoint_file.open() as f:
            data = json.load(f)

        assert data["batch_id"] == batch_id
        assert data["completed_files"] == completed_files
        assert data["metadata"] == metadata
        assert "timestamp" in data
        # Verify timestamp is ISO format
        assert "T" in data["timestamp"]

    def test_load_checkpoint_existing(self, checkpoint_manager):
        """Test load_checkpoint returns data for existing checkpoint."""
        batch_id = "test_batch_789"
        completed_files = ["/path/to/file1.pdf", "/path/to/file2.pdf", "/path/to/file3.pdf"]
        metadata = {"total": 10}

        checkpoint_manager.save_checkpoint(batch_id, completed_files, metadata)
        loaded_data = checkpoint_manager.load_checkpoint(batch_id)

        assert loaded_data is not None
        assert loaded_data["batch_id"] == batch_id
        assert loaded_data["completed_files"] == completed_files
        assert loaded_data["metadata"] == metadata
        assert "timestamp" in loaded_data

    def test_load_checkpoint_nonexistent(self, checkpoint_manager):
        """Test load_checkpoint returns None for missing checkpoint."""
        loaded_data = checkpoint_manager.load_checkpoint("nonexistent_batch")

        assert loaded_data is None

    def test_clear_checkpoint_removes_file(self, checkpoint_manager, temp_checkpoint_dir):
        """Test clear_checkpoint removes checkpoint file."""
        batch_id = "test_batch_clear"
        completed_files = ["/path/to/file1.pdf"]
        metadata = {"total": 5}

        checkpoint_manager.save_checkpoint(batch_id, completed_files, metadata)
        checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"
        assert checkpoint_file.exists()

        checkpoint_manager.clear_checkpoint(batch_id)

        assert not checkpoint_file.exists()

    def test_clear_checkpoint_missing_ok(self, checkpoint_manager):
        """Test clear_checkpoint doesn't error if file missing."""
        # Should not raise exception
        checkpoint_manager.clear_checkpoint("nonexistent_batch")


class TestCheckpointManagerRemainingFiles:
    """Test get_remaining_files logic."""

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def checkpoint_manager(self, temp_checkpoint_dir):
        """Create CheckpointManager instance."""
        return CheckpointManager(temp_checkpoint_dir)

    def test_get_remaining_files_no_checkpoint(self, checkpoint_manager):
        """Test returns all files when no checkpoint exists."""
        all_files = [
            Path("/path/to/file1.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file3.pdf"),
        ]

        remaining = checkpoint_manager.get_remaining_files("no_checkpoint", all_files)

        assert remaining == all_files

    def test_get_remaining_files_with_completed(self, checkpoint_manager):
        """Test returns only uncompleted files."""
        all_files = [
            Path("/path/to/file1.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file3.pdf"),
            Path("/path/to/file4.pdf"),
            Path("/path/to/file5.pdf"),
        ]
        completed = ["/path/to/file1.pdf", "/path/to/file2.pdf"]

        checkpoint_manager.save_checkpoint("batch_123", completed, {})
        remaining = checkpoint_manager.get_remaining_files("batch_123", all_files)

        assert len(remaining) == 3
        assert Path("/path/to/file3.pdf") in remaining
        assert Path("/path/to/file4.pdf") in remaining
        assert Path("/path/to/file5.pdf") in remaining
        assert Path("/path/to/file1.pdf") not in remaining
        assert Path("/path/to/file2.pdf") not in remaining

    def test_get_remaining_files_all_completed(self, checkpoint_manager):
        """Test returns empty list when all files completed."""
        all_files = [
            Path("/path/to/file1.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file3.pdf"),
        ]
        completed = [str(f) for f in all_files]

        checkpoint_manager.save_checkpoint("batch_456", completed, {})
        remaining = checkpoint_manager.get_remaining_files("batch_456", all_files)

        assert len(remaining) == 0

    def test_get_remaining_files_path_matching(self, checkpoint_manager):
        """Test file path matching is correct (str vs Path)."""
        # Save checkpoint with string paths
        completed_str = ["/path/to/file1.pdf", "/path/to/file2.pdf"]
        checkpoint_manager.save_checkpoint("batch_789", completed_str, {})

        # Query with Path objects
        all_files_paths = [
            Path("/path/to/file1.pdf"),
            Path("/path/to/file2.pdf"),
            Path("/path/to/file3.pdf"),
        ]

        remaining = checkpoint_manager.get_remaining_files("batch_789", all_files_paths)

        # Should correctly match string vs Path
        assert len(remaining) == 1
        assert Path("/path/to/file3.pdf") in remaining


class TestCheckpointManagerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create temporary checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def checkpoint_manager(self, temp_checkpoint_dir):
        """Create CheckpointManager instance."""
        return CheckpointManager(temp_checkpoint_dir)

    def test_save_checkpoint_overwrites_existing(self, checkpoint_manager):
        """Test save_checkpoint overwrites previous checkpoint."""
        batch_id = "batch_overwrite"

        # Save checkpoint with 3 files
        checkpoint_manager.save_checkpoint(batch_id, ["file1.pdf", "file2.pdf", "file3.pdf"], {})

        # Save checkpoint again with 5 files
        checkpoint_manager.save_checkpoint(
            batch_id,
            ["file1.pdf", "file2.pdf", "file3.pdf", "file4.pdf", "file5.pdf"],
            {"total": 10},
        )

        # Load checkpoint
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        # Should have 5 files, not 3
        assert len(loaded["completed_files"]) == 5
        assert loaded["metadata"]["total"] == 10

    def test_checkpoint_with_empty_completed_list(self, checkpoint_manager):
        """Test checkpoint with zero completed files."""
        batch_id = "batch_empty"

        checkpoint_manager.save_checkpoint(batch_id, [], {"total": 10})
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        assert loaded is not None
        assert loaded["completed_files"] == []
        assert loaded["metadata"]["total"] == 10

    def test_checkpoint_with_none_metadata(self, checkpoint_manager):
        """Test checkpoint with None metadata."""
        batch_id = "batch_none_metadata"

        checkpoint_manager.save_checkpoint(batch_id, ["file1.pdf"], None)
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        assert loaded is not None
        assert loaded["metadata"] == {}  # Should be empty dict, not None

    def test_checkpoint_with_special_characters_in_paths(self, checkpoint_manager):
        """Test file paths with spaces, unicode, special chars."""
        batch_id = "batch_special"
        special_paths = [
            "/path/with spaces/file.pdf",
            "/path/with-dashes/file.pdf",
            "/path/with_underscores/file.pdf",
            "/path/with.dots/file.pdf",
            "/path/with(parens)/file.pdf",
            "/path/with[brackets]/file.pdf",
            "/path/with'quotes/file.pdf",
            "/path/with unicode é ñ/file.pdf",
        ]

        checkpoint_manager.save_checkpoint(batch_id, special_paths, {})
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        assert loaded["completed_files"] == special_paths

        # Test get_remaining_files works with special chars
        all_files = [Path(p) for p in special_paths] + [Path("/path/normal/file.pdf")]
        remaining = checkpoint_manager.get_remaining_files(batch_id, all_files)

        assert len(remaining) == 1
        assert remaining[0] == Path("/path/normal/file.pdf")

    def test_corrupted_checkpoint_json(self, checkpoint_manager, temp_checkpoint_dir):
        """Test behavior when checkpoint JSON is corrupted."""
        batch_id = "batch_corrupted"
        checkpoint_file = temp_checkpoint_dir / f"{batch_id}.json"

        # Create corrupted JSON file
        checkpoint_file.write_text("{ this is not valid json }")

        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            checkpoint_manager.load_checkpoint(batch_id)

    def test_checkpoint_with_large_file_list(self, checkpoint_manager):
        """Test checkpoint with large number of files."""
        batch_id = "batch_large"
        # Create 1000 file paths
        large_file_list = [f"/path/to/file{i}.pdf" for i in range(1000)]

        checkpoint_manager.save_checkpoint(batch_id, large_file_list, {"total": 2000})
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        assert len(loaded["completed_files"]) == 1000
        assert loaded["metadata"]["total"] == 2000

    def test_multiple_checkpoints_different_batches(self, checkpoint_manager):
        """Test multiple checkpoints for different batches."""
        # Create 3 different checkpoints
        checkpoint_manager.save_checkpoint("batch_A", ["fileA1.pdf", "fileA2.pdf"], {})
        checkpoint_manager.save_checkpoint("batch_B", ["fileB1.pdf"], {})
        checkpoint_manager.save_checkpoint(
            "batch_C", ["fileC1.pdf", "fileC2.pdf", "fileC3.pdf"], {}
        )

        # Load each independently
        loaded_a = checkpoint_manager.load_checkpoint("batch_A")
        loaded_b = checkpoint_manager.load_checkpoint("batch_B")
        loaded_c = checkpoint_manager.load_checkpoint("batch_C")

        assert len(loaded_a["completed_files"]) == 2
        assert len(loaded_b["completed_files"]) == 1
        assert len(loaded_c["completed_files"]) == 3

        # Clear one checkpoint
        checkpoint_manager.clear_checkpoint("batch_B")

        # Others should still exist
        assert checkpoint_manager.load_checkpoint("batch_A") is not None
        assert checkpoint_manager.load_checkpoint("batch_B") is None
        assert checkpoint_manager.load_checkpoint("batch_C") is not None

    def test_checkpoint_preserves_file_order(self, checkpoint_manager):
        """Test checkpoint preserves order of completed files."""
        batch_id = "batch_order"
        files_in_order = [
            "/path/to/zebra.pdf",
            "/path/to/apple.pdf",
            "/path/to/middle.pdf",
        ]

        checkpoint_manager.save_checkpoint(batch_id, files_in_order, {})
        loaded = checkpoint_manager.load_checkpoint(batch_id)

        # Order should be preserved (not alphabetically sorted)
        assert loaded["completed_files"] == files_in_order
