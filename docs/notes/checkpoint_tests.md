# Checkpoint/Resume Testing Plan

**Created:** 2025-10-02
**Status:** DRAFT - Ready for Review
**Priority:** HIGH (Blocking production use)

---

## Problem Statement

The checkpoint/resume feature (Phase 2 of robustness) has **zero automated test coverage** despite being marked "COMPLETE" in `robustness.md`. The code exists and looks reasonable, but without tests we cannot trust it will work correctly in production scenarios.

**Critical untested components:**
- `CheckpointManager` class (save, load, clear, get_remaining_files)
- Signal handlers in `IngestionPipeline` (SIGINT/SIGTERM)
- Checkpoint/resume integration in `process_batch()`
- CLI `--resume` flag behavior
- Edge cases (corrupted checkpoints, permission errors, multiple interrupts)

---

## Testing Strategy

### Phase 1: Unit Tests (CheckpointManager)
**Goal:** Test checkpoint manager in isolation
**Duration:** ~2 hours
**Files to create:** `tests/unit/test_core/test_checkpoint_manager.py`

### Phase 2: Integration Tests (Pipeline Checkpoint/Resume)
**Goal:** Test checkpoint/resume in realistic pipeline scenarios
**Duration:** ~3 hours
**Files to create:** `tests/integration/test_pipelines/test_checkpoint_resume.py`

### Phase 3: Manual/E2E Validation
**Goal:** Test actual interrupt handling with real PDFs
**Duration:** ~1 hour
**Files to update:** `docs/notes/checkpoint_tests.md` (add results section)

---

## Phase 1: Unit Tests (CheckpointManager)

### Test File: `tests/unit/test_core/test_checkpoint_manager.py`

**Test Cases:**

#### 1.1 Basic Checkpoint Operations
```python
class TestCheckpointManagerBasics:
    def test_create_checkpoint_directory(self):
        """Test checkpoint directory is created."""
        # Create CheckpointManager with non-existent directory
        # Assert directory was created

    def test_save_checkpoint_creates_file(self):
        """Test save_checkpoint creates JSON file."""
        # Save checkpoint with batch_id, completed_files, metadata
        # Assert checkpoint file exists with correct name

    def test_save_checkpoint_content(self):
        """Test save_checkpoint writes correct JSON structure."""
        # Save checkpoint
        # Read file directly
        # Assert JSON contains: batch_id, completed_files, metadata, timestamp

    def test_load_checkpoint_existing(self):
        """Test load_checkpoint returns data for existing checkpoint."""
        # Save checkpoint
        # Load checkpoint
        # Assert loaded data matches saved data

    def test_load_checkpoint_nonexistent(self):
        """Test load_checkpoint returns None for missing checkpoint."""
        # Load checkpoint that doesn't exist
        # Assert returns None

    def test_clear_checkpoint_removes_file(self):
        """Test clear_checkpoint removes checkpoint file."""
        # Save checkpoint
        # Clear checkpoint
        # Assert file no longer exists

    def test_clear_checkpoint_missing_ok(self):
        """Test clear_checkpoint doesn't error if file missing."""
        # Clear checkpoint that doesn't exist
        # Assert no exception raised
```

#### 1.2 get_remaining_files Logic
```python
class TestCheckpointManagerRemainingFiles:
    def test_get_remaining_files_no_checkpoint(self):
        """Test returns all files when no checkpoint exists."""
        # Call get_remaining_files with no checkpoint saved
        # Assert returns all input files

    def test_get_remaining_files_with_completed(self):
        """Test returns only uncompleted files."""
        # Save checkpoint with 3 of 10 files completed
        # Call get_remaining_files with all 10 files
        # Assert returns only the 7 uncompleted files

    def test_get_remaining_files_all_completed(self):
        """Test returns empty list when all files completed."""
        # Save checkpoint with all files completed
        # Call get_remaining_files
        # Assert returns empty list

    def test_get_remaining_files_path_matching(self):
        """Test file path matching is correct (str vs Path)."""
        # Save checkpoint with string paths
        # Call get_remaining_files with Path objects
        # Assert matching works correctly (string conversion)
```

#### 1.3 Edge Cases
```python
class TestCheckpointManagerEdgeCases:
    def test_save_checkpoint_overwrites_existing(self):
        """Test save_checkpoint overwrites previous checkpoint."""
        # Save checkpoint with 3 files
        # Save checkpoint again with 5 files
        # Load checkpoint
        # Assert has 5 files, not 3

    def test_checkpoint_with_empty_completed_list(self):
        """Test checkpoint with zero completed files."""
        # Save checkpoint with empty completed_files list
        # Load checkpoint
        # Assert returns valid data structure

    def test_checkpoint_with_none_metadata(self):
        """Test checkpoint with None metadata."""
        # Save checkpoint with metadata=None
        # Load checkpoint
        # Assert metadata is empty dict, not None

    def test_checkpoint_with_special_characters_in_paths(self):
        """Test file paths with spaces, unicode, special chars."""
        # Save checkpoint with paths containing spaces, unicode
        # Load and get_remaining_files
        # Assert paths preserved correctly

    def test_corrupted_checkpoint_json(self):
        """Test behavior when checkpoint JSON is corrupted."""
        # Save checkpoint
        # Manually corrupt the JSON file
        # Attempt to load checkpoint
        # Assert raises JSONDecodeError (or returns None gracefully)
```

---

## Phase 2: Integration Tests (Pipeline Checkpoint/Resume)

### Test File: `tests/integration/test_pipelines/test_checkpoint_resume.py`

**Test Cases:**

#### 2.1 Basic Checkpoint/Resume Flow
```python
class TestIngestionPipelineCheckpointResume:
    def test_resume_from_checkpoint(self):
        """Test pipeline resumes from existing checkpoint."""
        # Create pipeline with mock extractor
        # Manually create checkpoint with 3 of 10 files completed
        # Call process_batch with resume=True
        # Assert only 7 files processed
        # Assert mock extractor called 7 times, not 10

    def test_no_resume_ignores_checkpoint(self):
        """Test resume=False ignores checkpoint."""
        # Create checkpoint with 3 files completed
        # Call process_batch with resume=False
        # Assert all 10 files processed (checkpoint ignored)

    def test_checkpoint_cleared_on_completion(self):
        """Test checkpoint file deleted after successful batch."""
        # Process batch to completion
        # Assert checkpoint file was deleted

    def test_checkpoint_message_shows_remaining_count(self):
        """Test resume displays correct count of remaining files."""
        # Create checkpoint with 3 of 10 completed
        # Capture log output
        # Call process_batch with resume=True
        # Assert log contains "7/10 files remaining"
```

#### 2.2 Batch ID Generation
```python
class TestBatchIdGeneration:
    def test_same_files_same_batch_id(self):
        """Test same file list generates same batch ID."""
        # Create pipeline
        # Manually generate batch_id from file list
        # Process batch
        # Assert checkpoint file uses expected batch_id

    def test_different_files_different_batch_id(self):
        """Test different file lists generate different batch IDs."""
        # Save checkpoint for batch A
        # Process batch B with different files
        # Assert batch B doesn't resume from batch A's checkpoint

    def test_file_order_affects_batch_id(self):
        """Test file order changes batch ID."""
        # Save checkpoint for [file1, file2, file3]
        # Process batch [file3, file2, file1]
        # Assert treated as different batch (different batch_id)
```

#### 2.3 Checkpoint State Tracking
```python
class TestCheckpointStateTracking:
    def test_completed_list_grows_correctly(self):
        """Test completed files tracked in checkpoint."""
        # Mock process_single_document to save checkpoint after each file
        # Process 3 files
        # Load checkpoint after each file
        # Assert completed_files list grows: [1], [1,2], [1,2,3]

    def test_metadata_stored_in_checkpoint(self):
        """Test checkpoint metadata contains batch info."""
        # Process batch (with simulated interrupt)
        # Load checkpoint
        # Assert metadata contains {"total": 10}

    def test_partial_completion_status(self):
        """Test checkpoint tracks success/error/skip status."""
        # Process batch with mix of success/error files
        # Simulate interrupt after 5 files
        # Resume batch
        # Assert remaining 5 files processed
        # Assert no duplicate processing
```

#### 2.4 Interrupt Simulation
```python
class TestInterruptHandling:
    def test_interrupted_flag_stops_processing(self):
        """Test setting interrupted=True stops batch."""
        # Process batch
        # Set pipeline.interrupted = True after 3 files
        # Assert only 3 files processed
        # Assert checkpoint saved with 3 files

    def test_checkpoint_saved_before_exit(self):
        """Test checkpoint saved when interrupted."""
        # Mock sys.exit to capture when called
        # Set interrupted=True during batch
        # Assert checkpoint file exists when exit called

    def test_interrupt_message_logged(self):
        """Test interrupt displays save message."""
        # Capture log output
        # Trigger interrupt
        # Assert log contains "💾 Saving checkpoint"
        # Assert log contains "(3/10 completed)"
```

**NOTE:** Actual signal testing (SIGINT/SIGTERM) is difficult in unit tests and better validated manually.

---

## Phase 3: Manual/E2E Validation

### Test Scenarios (Manual Execution)

#### 3.1 Real Interrupt with Ctrl+C
```bash
# Setup: Copy 20 small PDFs to test directory
mkdir -p /tmp/checkpoint_test
cp data/sample/*.pdf /tmp/checkpoint_test/

# Test 1: Interrupt and resume
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_interrupt

# Press Ctrl+C after ~5 files processed

# Verify checkpoint created
ls .checkpoints/
cat .checkpoints/*.json  # Check contains 5 completed files

# Resume processing
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_interrupt

# Verify:
# - Log shows "Resuming: X/20 files remaining"
# - Only remaining files processed
# - Checkpoint deleted on completion
# - No duplicate documents in database
```

#### 3.2 Multiple Interrupts
```bash
# Test 2: Interrupt twice, then complete
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_multi

# Ctrl+C after 5 files
# Resume
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_multi

# Ctrl+C after 3 more files (8 total)
# Resume and complete
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_multi

# Verify all 20 files processed exactly once
sqlite3 registry.db "SELECT COUNT(*) FROM documents WHERE project_id='test_multi';"
# Should output: 20
```

#### 3.3 No Resume Flag
```bash
# Test 3: --no-resume reprocesses all
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_noresume

# Ctrl+C after 5 files
# Verify checkpoint exists

# Resume with --no-resume
rkb extract /tmp/checkpoint_test/*.pdf --project-id test_noresume --no-resume

# Verify:
# - All 20 files processed (checkpoint ignored)
# - Existing 5 documents skipped (already in DB)
```

#### 3.4 Custom Checkpoint Directory
```bash
# Test 4: Custom checkpoint directory
rkb extract /tmp/checkpoint_test/*.pdf \
  --project-id test_custom \
  --checkpoint-dir /tmp/my_checkpoints

# Ctrl+C after 5 files
# Verify checkpoint in /tmp/my_checkpoints/
ls /tmp/my_checkpoints/

# Resume with same directory
rkb extract /tmp/checkpoint_test/*.pdf \
  --project-id test_custom \
  --checkpoint-dir /tmp/my_checkpoints

# Verify resume works correctly
```

### Manual Test Checklist

After running manual tests, verify:

- [ ] Ctrl+C displays interrupt message
- [ ] Checkpoint JSON file created in correct directory
- [ ] Checkpoint contains correct completed file count
- [ ] Checkpoint contains metadata (total file count)
- [ ] Checkpoint timestamp is valid ISO format
- [ ] Resume displays "Resuming: X/Y files remaining" message
- [ ] Resume processes only remaining files
- [ ] Resume does not create duplicate documents in database
- [ ] Checkpoint deleted after successful completion
- [ ] Multiple interrupt/resume cycles work correctly
- [ ] `--no-resume` flag ignores checkpoint
- [ ] `--checkpoint-dir` flag uses custom directory
- [ ] Batch ID is consistent for same file list
- [ ] Different file lists create different checkpoints

---

## Acceptance Criteria

### For Unit Tests (Phase 1)
- [ ] All 20+ unit tests passing
- [ ] 100% line coverage of `CheckpointManager` class
- [ ] ruff check passes
- [ ] lint-imports passes

### For Integration Tests (Phase 2)
- [ ] All 15+ integration tests passing
- [ ] Tests cover resume=True and resume=False
- [ ] Tests verify checkpoint creation, loading, deletion
- [ ] Tests verify batch_id generation logic
- [ ] ruff check passes
- [ ] lint-imports passes

### For Manual Validation (Phase 3)
- [ ] All 12 manual test checklist items verified
- [ ] Results documented in this file (add "Manual Test Results" section)
- [ ] No duplicate documents created during resume
- [ ] No data corruption in database
- [ ] Checkpoint files cleaned up properly

---

## Implementation Steps

### Step 1: Write Unit Tests (2 hours)
1. Create `tests/unit/test_core/test_checkpoint_manager.py`
2. Implement all test cases from Phase 1
3. Run: `pytest tests/unit/test_core/test_checkpoint_manager.py -v`
4. Verify all tests pass
5. Run: `ruff check tests/unit/test_core/test_checkpoint_manager.py`

### Step 2: Write Integration Tests (3 hours)
1. Create `tests/integration/test_pipelines/test_checkpoint_resume.py`
2. Implement all test cases from Phase 2
3. Run: `pytest tests/integration/test_pipelines/test_checkpoint_resume.py -v`
4. Verify all tests pass
5. Run: `lint-imports`

### Step 3: Manual Validation (1 hour)
1. Run all 4 manual test scenarios
2. Check all items in manual test checklist
3. Document results below (add section)
4. Fix any bugs discovered
5. Re-run tests to verify fixes

### Step 4: Update Documentation
1. Update `robustness.md` with test coverage results
2. Mark checkpoint/resume as "TESTED ✅"
3. Update this file with manual test results

---

## Risks and Edge Cases

### Identified Risks
1. **Signal handlers in tests**: Hard to test SIGINT/SIGTERM in unit tests
   - **Mitigation**: Test `interrupted` flag directly, validate signals manually

2. **File system race conditions**: Checkpoint file written during crash
   - **Mitigation**: Test corrupted JSON handling

3. **Concurrent batch processing**: Multiple processes, same batch_id
   - **Mitigation**: Document that concurrent processing is not supported (add to robustness.md)

4. **Checkpoint directory permissions**: No write access
   - **Mitigation**: Add test for permission errors

5. **Very large file lists**: Batch ID collision or memory issues
   - **Mitigation**: Test with 1000+ file list

### Edge Cases to Cover
- [ ] Empty file list (0 files)
- [ ] Single file (1 file)
- [ ] All files already processed (skip all)
- [ ] Checkpoint with 0 completed files
- [ ] Checkpoint with all files completed
- [ ] File paths with spaces, unicode, special characters
- [ ] Corrupted checkpoint JSON
- [ ] Missing checkpoint directory (permissions)
- [ ] Batch processing interrupted on first file
- [ ] Batch processing interrupted on last file

---

## Expected Test Count

### Unit Tests: ~25 tests
- Basic operations: 7 tests
- get_remaining_files: 4 tests
- Edge cases: 8 tests
- Additional coverage: 6 tests

### Integration Tests: ~15 tests
- Basic checkpoint/resume: 4 tests
- Batch ID generation: 3 tests
- State tracking: 3 tests
- Interrupt handling: 5 tests

### Manual Tests: 4 scenarios
- Real interrupt with Ctrl+C
- Multiple interrupts
- --no-resume flag
- Custom checkpoint directory

**Total: ~40 automated tests + 4 manual scenarios**

---

## Success Metrics

After completing all phases, we should be able to confidently answer YES to:

1. ✅ Can I interrupt a large extraction job and resume it?
2. ✅ Will checkpoint/resume avoid duplicate processing?
3. ✅ Will checkpoint files be cleaned up correctly?
4. ✅ Does the system handle corrupted checkpoints gracefully?
5. ✅ Does `--resume` flag work as documented?
6. ✅ Does `--no-resume` flag work as documented?
7. ✅ Can I use a custom checkpoint directory?
8. ✅ Are there no memory leaks or resource issues?

**Current Status**: ❌ Cannot confidently answer YES to any of these (no tests)

**After Testing**: ✅ Can confidently answer YES to all (40+ tests + manual validation)

---

## Timeline

- **Step 1 (Unit Tests)**: 2 hours
- **Step 2 (Integration Tests)**: 3 hours
- **Step 3 (Manual Validation)**: 1 hour
- **Step 4 (Documentation)**: 0.5 hours

**Total Estimated Time**: 6.5 hours (can be split across multiple sessions)

---

## Next Actions

1. **Review this plan** - Does it cover all critical scenarios?
2. **Prioritize phases** - Can we skip any tests? (Recommendation: No, all are critical)
3. **Schedule implementation** - When to implement? (Recommendation: Before any large-scale production use)
4. **Assign owner** - Who will implement? (You or Claude?)

---

## Notes

- Signal handler testing (SIGINT/SIGTERM) is deliberately tested manually rather than in unit tests due to complexity and flakiness of signal testing in pytest
- The `interrupted` flag mechanism is tested in integration tests as a proxy for signal handling
- Batch ID generation uses MD5 hash, which is sufficient for checkpoint identification (no security requirement)
- Checkpoint files are plain JSON for debuggability (not binary)
- No encryption/signing of checkpoints (not a security boundary)
