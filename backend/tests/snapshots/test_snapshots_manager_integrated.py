"""
Integrated tests for ResticManager using real restic commands.

These tests use actual restic operations to ensure the snapshot system works correctly.
Tests create temporary directories and repositories to avoid affecting real data.

IMPORTANT: These tests require restic to be installed on the system.
Run with: poetry run pytest tests/snapshots/test_snapshots_manager_integrated.py -v
"""

import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from app.snapshots import ResticManager
from app.utils.exec import exec_command


# Helper function to check if restic is available
def check_restic_available():
    """Check if restic command is available"""
    try:
        result = subprocess.run(
            ["restic", "version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Skip all tests if restic is not available
pytestmark = pytest.mark.skipif(
    not check_restic_available(),
    reason="restic command not available - install restic to run these tests",
)


class TestResticManagerIntegrated:
    """Integrated tests using real restic commands and temporary directories"""

    @pytest.fixture
    def temp_repo_dir(self):
        """Create temporary directory for restic repository"""
        with tempfile.TemporaryDirectory(prefix="restic_test_repo_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def temp_backup_dir(self):
        """Create temporary directory with test files for backup"""
        with tempfile.TemporaryDirectory(prefix="restic_test_backup_") as temp_dir:
            backup_dir = Path(temp_dir)

            # Create test files with specific content for verification
            (backup_dir / "test_file1.txt").write_text(
                "Original content of file 1\nSecond line"
            )
            (backup_dir / "test_file2.txt").write_text(
                "Original content of file 2\nAnother line"
            )

            # Create subdirectory with nested file
            subdir = backup_dir / "nested_dir"
            subdir.mkdir()
            (subdir / "nested_file.txt").write_text("Nested file original content")

            # Create binary file for testing
            binary_data = bytes(range(256))
            (backup_dir / "binary_file.bin").write_bytes(binary_data)

            yield backup_dir

    @pytest.fixture
    async def restic_manager(self, temp_repo_dir):
        """Create ResticManager and initialize repository"""
        manager = ResticManager(
            repository_path=str(temp_repo_dir), password="test-secure-password-123"
        )

        # Initialize the repository
        try:
            await exec_command("restic", "init", env=manager.env)
        except Exception as e:
            pytest.fail(f"Failed to initialize restic repository: {e}")

        return manager

    @pytest.mark.asyncio
    async def test_basic_backup_and_list(self, restic_manager, temp_backup_dir):
        """Test basic backup creation and listing"""
        manager = restic_manager

        # Create backup
        snapshot = await manager.backup(temp_backup_dir)

        # Verify snapshot properties
        assert snapshot.id is not None
        assert len(snapshot.id) == 64  # SHA256 hash length
        assert snapshot.short_id is not None
        assert len(snapshot.short_id) == 8
        assert str(temp_backup_dir) in snapshot.paths
        assert snapshot.hostname is not None
        assert snapshot.username is not None
        assert isinstance(snapshot.time, datetime)

        # Verify snapshot summary contains expected data
        if snapshot.summary:
            assert snapshot.summary.files_new >= 4  # We created 4 files
            assert snapshot.summary.total_files_processed >= 4
            assert snapshot.summary.total_bytes_processed > 0

        # List snapshots
        snapshots = await manager.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot.id
        assert snapshots[0].paths == snapshot.paths

    @pytest.mark.asyncio
    async def test_backup_content_integrity(self, restic_manager, temp_backup_dir):
        """Test that backup preserves file content correctly"""
        manager = restic_manager

        # Record original content
        original_files = {}
        for file_path in temp_backup_dir.rglob("*"):
            if file_path.is_file():
                if file_path.suffix == ".bin":
                    original_files[str(file_path.relative_to(temp_backup_dir))] = (
                        file_path.read_bytes()
                    )
                else:
                    original_files[str(file_path.relative_to(temp_backup_dir))] = (
                        file_path.read_text()
                    )

        # Create backup
        snapshot = await manager.backup(temp_backup_dir)

        # Modify original files
        (temp_backup_dir / "test_file1.txt").write_text("MODIFIED CONTENT")
        (temp_backup_dir / "test_file2.txt").write_text("ALSO MODIFIED")
        (temp_backup_dir / "nested_dir" / "nested_file.txt").write_text(
            "NESTED MODIFIED"
        )

        # Create restore target directory
        with tempfile.TemporaryDirectory(prefix="restic_restore_") as restore_dir:
            restore_path = Path(restore_dir)

            # Restore snapshot
            await manager.restore(
                snapshot_id=snapshot.id,
                target_path=restore_path,
                include_path=temp_backup_dir,
            )

            # Verify restored content matches original
            # restic restores with full absolute path structure
            restored_backup_dir = restore_path / temp_backup_dir.relative_to(Path("/"))
            for rel_path, original_content in original_files.items():
                restored_file = restored_backup_dir / rel_path
                assert restored_file.exists(), f"File {rel_path} was not restored"

                if isinstance(original_content, bytes):
                    assert restored_file.read_bytes() == original_content
                else:
                    assert restored_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_restore_preview_functionality(self, restic_manager, temp_backup_dir):
        """Test restore preview shows correct information"""
        manager = restic_manager

        # Create initial backup
        snapshot = await manager.backup(temp_backup_dir)

        # Modify files to create changes
        (temp_backup_dir / "test_file1.txt").write_text("Modified for preview test")

        # Add new file
        (temp_backup_dir / "new_file.txt").write_text("New file for testing")

        # Remove existing file
        (temp_backup_dir / "test_file2.txt").unlink()

        # Preview restore
        actions = await manager.restore_preview(
            snapshot_id=snapshot.id, target_path=Path("/"), include_path=temp_backup_dir
        )

        # Verify preview provides meaningful information
        assert len(actions) > 0, "Preview should show actions to be performed"

        # Check that actions contain expected types
        action_types = {action.action for action in actions}
        expected_types = {"updated", "restored", "deleted"}
        assert len(action_types.intersection(expected_types)) > 0

        # Verify all actions have required fields
        for action in actions:
            assert action.message_type == "verbose_status"
            assert action.action in ["updated", "restored", "deleted"]
            assert action.item is not None
            # Size validation: deleted operations can have size 0, but others should be > 0
            if action.action == "deleted":
                assert action.size is not None and action.size >= 0
            else:
                assert action.size is not None and action.size > 0
            assert (
                str(temp_backup_dir) in action.item
            )  # Should be related to our test data

    @pytest.mark.asyncio
    async def test_in_place_restore(self, restic_manager, temp_backup_dir):
        """Test in-place restore functionality"""
        manager = restic_manager

        # Record original content
        original_content = (temp_backup_dir / "test_file1.txt").read_text()

        # Create backup
        snapshot = await manager.backup(temp_backup_dir)

        # Modify files
        (temp_backup_dir / "test_file1.txt").write_text("Modified for in-place test")
        (temp_backup_dir / "extra_file.txt").write_text("Extra file to be deleted")

        # Verify modification
        modified_content = (temp_backup_dir / "test_file1.txt").read_text()
        assert modified_content != original_content
        assert (temp_backup_dir / "extra_file.txt").exists()

        # Perform in-place restore
        await manager.restore(
            snapshot_id=snapshot.id,
            target_path=Path("/"),  # Root for in-place restore
            include_path=temp_backup_dir,
        )

        # Verify restoration
        restored_content = (temp_backup_dir / "test_file1.txt").read_text()
        assert restored_content == original_content

        # Verify extra file was deleted (because of --delete flag)
        assert not (temp_backup_dir / "extra_file.txt").exists()

    @pytest.mark.asyncio
    async def test_path_filtering(self, restic_manager, temp_backup_dir):
        """Test snapshot filtering by path"""
        manager = restic_manager

        # Create snapshots of different scopes
        subdir = temp_backup_dir / "nested_dir"

        # Backup entire directory
        snapshot_full = await manager.backup(temp_backup_dir)

        # Backup just subdirectory
        snapshot_sub = await manager.backup(subdir)

        # List all snapshots
        all_snapshots = await manager.list_snapshots()
        assert len(all_snapshots) == 2

        # Filter by main directory - should include snapshot that covers it
        main_filtered = await manager.list_snapshots(path_filter=temp_backup_dir)
        main_ids = {s.id for s in main_filtered}
        assert snapshot_full.id in main_ids

        # Filter by subdirectory - should include both (full backup covers subdir too)
        sub_filtered = await manager.list_snapshots(path_filter=subdir)
        sub_ids = {s.id for s in sub_filtered}
        assert snapshot_full.id in sub_ids  # Full backup includes subdirectory
        assert snapshot_sub.id in sub_ids  # Direct subdirectory backup


    @pytest.mark.asyncio
    async def test_multiple_snapshots_chronology(self, restic_manager, temp_backup_dir):
        """Test multiple snapshots with chronological order"""
        manager = restic_manager

        snapshots_created = []

        # Create multiple snapshots with changes
        for i in range(3):
            # Modify content
            (temp_backup_dir / "test_file1.txt").write_text(f"Version {i + 1} content")

            # Create snapshot
            snapshot = await manager.backup(temp_backup_dir)
            snapshots_created.append(snapshot)

            # Small delay to ensure different timestamps
            time.sleep(0.1)

        # List all snapshots
        all_snapshots = await manager.list_snapshots()
        assert len(all_snapshots) == 3

        # Verify snapshots are ordered by time (newer first is typical)
        snapshot_times = [s.time for s in all_snapshots]
        assert len(set(snapshot_times)) == 3  # All different timestamps

        # Verify we can restore from any specific snapshot
        for i, created_snapshot in enumerate(snapshots_created):
            with tempfile.TemporaryDirectory() as restore_dir:
                restore_path = Path(restore_dir)

                await manager.restore(
                    snapshot_id=created_snapshot.id,
                    target_path=restore_path,
                    include_path=temp_backup_dir,
                )

                # Verify content matches the version when snapshot was created
                restored_file_path = (
                    restore_path
                    / temp_backup_dir.relative_to(Path("/"))
                    / "test_file1.txt"
                )
                restored_content = restored_file_path.read_text()
                assert restored_content == f"Version {i + 1} content"

    @pytest.mark.asyncio
    async def test_forget_functionality(self, restic_manager, temp_backup_dir):
        """Test forget functionality with keep_last parameter"""
        manager = restic_manager

        # Create multiple snapshots
        snapshots_created = []
        for i in range(5):
            (temp_backup_dir / "test_file.txt").write_text(f"Version {i + 1}")
            snapshot = await manager.backup(temp_backup_dir)
            snapshots_created.append(snapshot)
            time.sleep(0.1)  # Ensure different timestamps

        # Verify we have 5 snapshots
        all_snapshots = await manager.list_snapshots()
        assert len(all_snapshots) == 5

        # Forget snapshots, keeping only the last 1
        await manager.forget(keep_last=1, prune=True)

        # Verify only 1 snapshot remains
        remaining_snapshots = await manager.list_snapshots()
        assert len(remaining_snapshots) == 1

        # Verify the remaining snapshot is the most recent one
        remaining_snapshot = remaining_snapshots[0]
        most_recent_snapshot = snapshots_created[-1]
        assert remaining_snapshot.id == most_recent_snapshot.id

    @pytest.mark.asyncio
    async def test_error_handling_real(self, restic_manager, temp_backup_dir):
        """Test error handling with real restic operations"""
        manager = restic_manager

        # Test invalid snapshot ID
        with pytest.raises(RuntimeError):
            await manager.restore(
                snapshot_id="invalid-snapshot-id-123",
                target_path=Path("/tmp"),
                include_path=temp_backup_dir,
            )

        # Test backup of non-existent path
        nonexistent_path = Path("/tmp/nonexistent-" + str(int(time.time())))
        with pytest.raises((RuntimeError, ValueError)):
            await manager.backup(nonexistent_path)

    @pytest.mark.asyncio
    async def test_relative_path_rejection(self, restic_manager):
        """Test that relative paths are rejected"""
        manager = restic_manager

        relative_path = Path("relative/path/test")

        with pytest.raises(ValueError, match="Path must be absolute"):
            await manager.backup(relative_path)

    @pytest.mark.asyncio
    async def test_backup_empty_directory(self, restic_manager):
        """Test backing up empty directory"""
        with tempfile.TemporaryDirectory(prefix="empty_test_") as temp_dir:
            empty_dir = Path(temp_dir)

            # Backup empty directory
            snapshot = await restic_manager.backup(empty_dir)

            # Verify snapshot was created
            assert snapshot.id is not None
            assert str(empty_dir) in snapshot.paths

            # Should have minimal file count
            if snapshot.summary:
                assert snapshot.summary.total_files_processed >= 0

    @pytest.mark.asyncio
    async def test_large_file_handling(self, restic_manager):
        """Test handling of larger files"""
        with tempfile.TemporaryDirectory(prefix="large_file_test_") as temp_dir:
            test_dir = Path(temp_dir)

            # Create a reasonably large file (1MB)
            large_content = "A" * (1024 * 1024)  # 1MB of 'A' characters
            large_file = test_dir / "large_file.txt"
            large_file.write_text(large_content)

            # Backup
            snapshot = await restic_manager.backup(test_dir)

            # Verify backup includes the large file
            assert snapshot.summary.total_bytes_processed >= len(large_content)

            # Test restore
            with tempfile.TemporaryDirectory() as restore_dir:
                restore_path = Path(restore_dir)

                await restic_manager.restore(
                    snapshot_id=snapshot.id,
                    target_path=restore_path,
                    include_path=test_dir,
                )

                # Verify large file was restored correctly
                # Use correct path structure (full absolute path)
                restored_file = (
                    restore_path / test_dir.relative_to(Path("/")) / "large_file.txt"
                )
                assert restored_file.read_text() == large_content

    @pytest.mark.asyncio
    async def test_list_locks_no_locks(self, restic_manager):
        """Test list_locks when no locks exist"""
        manager = restic_manager

        # List locks (should be empty or complete successfully)
        locks_output = await manager.list_locks()

        # Should return a string (even if empty)
        assert isinstance(locks_output, str)

    @pytest.mark.asyncio
    async def test_unlock_no_locks(self, restic_manager):
        """Test unlock when no locks exist"""
        manager = restic_manager

        # Unlock should complete successfully even with no locks
        unlock_output = await manager.unlock()

        # Should return a string
        assert isinstance(unlock_output, str)
