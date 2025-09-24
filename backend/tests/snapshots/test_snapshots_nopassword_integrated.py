"""
Integrated tests for ResticManager without password using real restic commands.

These tests use actual restic operations to ensure the snapshot system works correctly
without password protection. Tests create temporary directories and repositories.

IMPORTANT: These tests require restic to be installed on the system.
Run with: poetry run pytest tests/snapshots/test_snapshots_nopassword_integrated.py -v
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


class TestResticManagerNoPasswordIntegrated:
    """Integrated tests for ResticManager without password using real restic commands"""

    @pytest.fixture
    def temp_repo_dir_no_password(self):
        """Create temporary directory for restic repository without password"""
        with tempfile.TemporaryDirectory(prefix="restic_test_repo_nopass_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def temp_backup_dir_no_password(self):
        """Create temporary directory with test files for backup"""
        with tempfile.TemporaryDirectory(
            prefix="restic_test_backup_nopass_"
        ) as temp_dir:
            backup_dir = Path(temp_dir)

            # Create test files
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

            yield backup_dir

    @pytest.fixture
    async def restic_manager_no_password(self, temp_repo_dir_no_password):
        """Create ResticManager without password and initialize repository"""
        manager = ResticManager(
            repository_path=str(temp_repo_dir_no_password), password=None
        )

        # Initialize the repository without password
        try:
            await exec_command(
                "restic", "init", "--insecure-no-password", env=manager.env
            )
        except Exception as e:
            pytest.fail(f"Failed to initialize restic repository without password: {e}")

        return manager

    @pytest.mark.asyncio
    async def test_backup_and_list_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test basic backup creation and listing without password"""
        manager = restic_manager_no_password

        # Create backup
        snapshot = await manager.backup(temp_backup_dir_no_password)

        # Verify snapshot properties
        assert snapshot.id is not None
        assert len(snapshot.id) == 64  # SHA256 hash length
        assert snapshot.short_id is not None
        assert len(snapshot.short_id) == 8
        assert str(temp_backup_dir_no_password) in snapshot.paths
        assert snapshot.hostname is not None
        assert snapshot.username is not None
        assert isinstance(snapshot.time, datetime)

        # List snapshots
        snapshots = await manager.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot.id
        assert snapshots[0].paths == snapshot.paths

    @pytest.mark.asyncio
    async def test_restore_preview_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test restore preview functionality without password"""
        manager = restic_manager_no_password

        # Create initial backup
        snapshot = await manager.backup(temp_backup_dir_no_password)

        # Modify files to create changes
        (temp_backup_dir_no_password / "test_file1.txt").write_text(
            "Modified for preview test"
        )

        # Preview restore
        actions = await manager.restore_preview(
            snapshot_id=snapshot.id,
            target_path=Path("/"),
            include_path=temp_backup_dir_no_password,
        )

        # Verify preview provides meaningful information
        assert len(actions) > 0, "Preview should show actions to be performed"

        # Verify all actions have required fields
        for action in actions:
            assert action.message_type == "verbose_status"
            assert action.action in ["updated", "restored", "deleted"]
            assert action.item is not None

    @pytest.mark.asyncio
    async def test_restore_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test actual restore functionality without password"""
        manager = restic_manager_no_password

        # Record original content
        original_content = (temp_backup_dir_no_password / "test_file1.txt").read_text()

        # Create backup
        snapshot = await manager.backup(temp_backup_dir_no_password)

        # Modify files
        (temp_backup_dir_no_password / "test_file1.txt").write_text(
            "Modified for restore test"
        )
        (temp_backup_dir_no_password / "extra_file.txt").write_text(
            "Extra file to be deleted"
        )

        # Verify modification
        modified_content = (temp_backup_dir_no_password / "test_file1.txt").read_text()
        assert modified_content != original_content
        assert (temp_backup_dir_no_password / "extra_file.txt").exists()

        # Perform in-place restore
        await manager.restore(
            snapshot_id=snapshot.id,
            target_path=Path("/"),  # Root for in-place restore
            include_path=temp_backup_dir_no_password,
        )

        # Verify restoration
        restored_content = (temp_backup_dir_no_password / "test_file1.txt").read_text()
        assert restored_content == original_content

        # Verify extra file was deleted (because of --delete flag)
        assert not (temp_backup_dir_no_password / "extra_file.txt").exists()

    @pytest.mark.asyncio
    async def test_forget_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test forget functionality without password"""
        manager = restic_manager_no_password

        # Create multiple snapshots
        snapshots_created = []
        for i in range(3):
            (temp_backup_dir_no_password / "test_file.txt").write_text(
                f"Version {i + 1}"
            )
            snapshot = await manager.backup(temp_backup_dir_no_password)
            snapshots_created.append(snapshot)
            time.sleep(0.1)  # Ensure different timestamps

        # Verify we have 3 snapshots
        all_snapshots = await manager.list_snapshots()
        assert len(all_snapshots) == 3

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
    async def test_has_recent_snapshot_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test recent snapshot detection without password"""
        manager = restic_manager_no_password

        # Initially no snapshots
        has_recent = await manager.has_recent_snapshot(
            temp_backup_dir_no_password, max_age_seconds=60
        )
        assert has_recent is False

        # Create snapshot
        await manager.backup(temp_backup_dir_no_password)

        # Should detect recent snapshot
        has_recent = await manager.has_recent_snapshot(
            temp_backup_dir_no_password, max_age_seconds=60
        )
        assert has_recent is True

    @pytest.mark.asyncio
    async def test_path_filtering_no_password(
        self, restic_manager_no_password, temp_backup_dir_no_password
    ):
        """Test snapshot filtering by path without password"""
        manager = restic_manager_no_password

        # Create snapshots of different scopes
        subdir = temp_backup_dir_no_password / "nested_dir"

        # Backup entire directory
        snapshot_full = await manager.backup(temp_backup_dir_no_password)

        # Backup just subdirectory
        snapshot_sub = await manager.backup(subdir)

        # List all snapshots
        all_snapshots = await manager.list_snapshots()
        assert len(all_snapshots) == 2

        # Filter by main directory - should include snapshot that covers it
        main_filtered = await manager.list_snapshots(
            path_filter=temp_backup_dir_no_password
        )
        main_ids = {s.id for s in main_filtered}
        assert snapshot_full.id in main_ids

        # Filter by subdirectory - should include both (full backup covers subdir too)
        sub_filtered = await manager.list_snapshots(path_filter=subdir)
        sub_ids = {s.id for s in sub_filtered}
        assert snapshot_full.id in sub_ids  # Full backup includes subdirectory
        assert snapshot_sub.id in sub_ids  # Direct subdirectory backup
