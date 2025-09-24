"""
Unit tests for common file operations module.
Tests the shared file operations utilities used by both servers and archive endpoints.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.files import (
    CreateFileRequest,
    FileItem,
    FileListResponse,
    RenameFileRequest,
    create_file_or_directory,
    delete_file_or_directory,
    get_file_content,
    get_file_items,
    rename_file_or_directory,
    update_file_content,
    upload_file,
)


class MockUploadFile(UploadFile):
    """Mock UploadFile for testing."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content
        self._pos = 0

    async def read(
        self,
        size: int = -1,
    ) -> bytes:
        if self._pos >= len(self._content):
            return b""
        if size == -1:
            result = self._content[self._pos :]
            self._pos = len(self._content)
            return result
        else:
            result = self._content[self._pos : self._pos + size]
            self._pos += size
            return result


class TestCommonFileOperations:
    """Test common file operations utilities."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory(
            prefix="mc_admin_common_file_test_", dir="/tmp"
        ) as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def test_structure(self, temp_dir):
        """Create test file and directory structure."""
        base_path = temp_dir / "test_base"
        base_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        (base_path / "config.txt").write_text("server_port=25565\nmax_players=20\n")
        (base_path / "data.json").write_text('{"server": {"name": "Test Server"}}')
        (base_path / "binary.dat").write_bytes(b"\x00\x01\x02\x03\x04\x05")

        # Create directories
        (base_path / "plugins").mkdir(exist_ok=True)
        (base_path / "worlds").mkdir(exist_ok=True)

        # Create nested files
        (base_path / "plugins" / "plugin.yml").write_text(
            "name: TestPlugin\nversion: 1.0\n"
        )
        (base_path / "worlds" / "world.dat").write_bytes(b"\x10\x20\x30\x40")

        return base_path

    @pytest.mark.asyncio
    async def test_get_file_items_root(self, test_structure):
        """Test getting file items from root directory."""
        base_path = test_structure
        items = await get_file_items(base_path, "/")

        assert len(items) > 0

        # Check that we have both files and directories
        files = [item for item in items if item.type == "file"]
        directories = [item for item in items if item.type == "directory"]

        assert len(files) >= 3  # config.txt, data.json, binary.dat
        assert len(directories) >= 2  # plugins, worlds

        # Check specific files
        file_names = {f.name for f in files}
        assert "config.txt" in file_names
        assert "data.json" in file_names
        assert "binary.dat" in file_names

        # Check directories
        dir_names = {d.name for d in directories}
        assert "plugins" in dir_names
        assert "worlds" in dir_names

    @pytest.mark.asyncio
    async def test_get_file_items_subdirectory(self, test_structure):
        """Test getting file items from subdirectory."""
        base_path = test_structure
        items = await get_file_items(base_path, "/plugins")

        assert len(items) >= 1

        plugin_file = next(item for item in items if item.name == "plugin.yml")
        assert plugin_file.type == "file"
        assert plugin_file.path == "/plugins/plugin.yml"

    @pytest.mark.asyncio
    async def test_get_file_items_nonexistent_path(self, test_structure):
        """Test getting file items from nonexistent path."""
        base_path = test_structure
        items = await get_file_items(base_path, "/nonexistent")

        assert items == []

    @pytest.mark.asyncio
    async def test_get_file_content_text(self, test_structure):
        """Test getting content of text file."""
        base_path = test_structure
        content = await get_file_content(base_path, "/config.txt")

        assert "server_port=25565" in content
        assert "max_players=20" in content

    @pytest.mark.asyncio
    async def test_get_file_content_nonexistent(self, test_structure):
        """Test getting content of nonexistent file."""
        base_path = test_structure

        with pytest.raises(HTTPException) as exc_info:
            await get_file_content(base_path, "/nonexistent.txt")

        assert exc_info.value.status_code == 404
        assert "File not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_file_content_directory(self, test_structure):
        """Test getting content of directory (should fail)."""
        base_path = test_structure

        with pytest.raises(HTTPException) as exc_info:
            await get_file_content(base_path, "/plugins")

        assert exc_info.value.status_code == 400
        assert "Path is not a file" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_file_content(self, test_structure):
        """Test updating file content."""
        base_path = test_structure
        new_content = "server_port=25566\nmax_players=30\nmotd=Updated Server\n"

        await update_file_content(base_path, "/config.txt", new_content)

        # Verify content was updated
        updated_content = (base_path / "config.txt").read_text()
        assert updated_content == new_content

    @pytest.mark.asyncio
    async def test_update_file_content_nonexistent(self, test_structure):
        """Test updating nonexistent file."""
        base_path = test_structure

        with pytest.raises(HTTPException) as exc_info:
            await update_file_content(base_path, "/nonexistent.txt", "content")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_file_new(self, test_structure):
        """Test uploading new file."""
        base_path = test_structure
        test_content = b"This is uploaded file content"
        mock_file = MockUploadFile("uploaded.txt", test_content)

        filename = await upload_file(base_path, "/", mock_file, allow_overwrite=False)

        assert filename == "uploaded.txt"

        # Verify file was created
        uploaded_file = base_path / "uploaded.txt"
        assert uploaded_file.exists()
        assert uploaded_file.read_bytes() == test_content

    @pytest.mark.asyncio
    async def test_upload_file_to_subdirectory(self, test_structure):
        """Test uploading file to subdirectory."""
        base_path = test_structure
        test_content = b"Plugin content"
        mock_file = MockUploadFile("new_plugin.jar", test_content)

        filename = await upload_file(
            base_path, "/plugins", mock_file, allow_overwrite=False
        )

        assert filename == "new_plugin.jar"

        # Verify file was created in subdirectory
        uploaded_file = base_path / "plugins" / "new_plugin.jar"
        assert uploaded_file.exists()
        assert uploaded_file.read_bytes() == test_content

    @pytest.mark.asyncio
    async def test_upload_file_exists_no_overwrite(self, test_structure):
        """Test uploading file that exists without overwrite."""
        base_path = test_structure
        mock_file = MockUploadFile("config.txt", b"content")

        with pytest.raises(HTTPException) as exc_info:
            await upload_file(base_path, "/", mock_file, allow_overwrite=False)

        assert exc_info.value.status_code == 409
        assert "File already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upload_file_exists_with_overwrite(self, test_structure):
        """Test uploading file that exists with overwrite allowed."""
        base_path = test_structure
        new_content = b"Overwritten content"
        mock_file = MockUploadFile("config.txt", new_content)

        filename = await upload_file(base_path, "/", mock_file, allow_overwrite=True)

        assert filename == "config.txt"

        # Verify file was overwritten
        uploaded_file = base_path / "config.txt"
        assert uploaded_file.read_bytes() == new_content

    @pytest.mark.asyncio
    async def test_create_file(self, test_structure):
        """Test creating new file."""
        base_path = test_structure
        create_request = CreateFileRequest(name="new_file.txt", type="file", path="/")

        message = await create_file_or_directory(base_path, create_request)

        assert "created successfully" in message

        # Verify file was created
        new_file = base_path / "new_file.txt"
        assert new_file.exists()
        assert new_file.is_file()

    @pytest.mark.asyncio
    async def test_create_directory(self, test_structure):
        """Test creating new directory."""
        base_path = test_structure
        create_request = CreateFileRequest(name="new_dir", type="directory", path="/")

        message = await create_file_or_directory(base_path, create_request)

        assert "created successfully" in message

        # Verify directory was created
        new_dir = base_path / "new_dir"
        assert new_dir.exists()
        assert new_dir.is_dir()

    @pytest.mark.asyncio
    async def test_create_file_already_exists(self, test_structure):
        """Test creating file that already exists."""
        base_path = test_structure
        create_request = CreateFileRequest(name="config.txt", type="file", path="/")

        with pytest.raises(HTTPException) as exc_info:
            await create_file_or_directory(base_path, create_request)

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_file(self, test_structure):
        """Test deleting file."""
        base_path = test_structure

        message = await delete_file_or_directory(base_path, "/data.json")

        assert "deleted successfully" in message

        # Verify file was deleted
        deleted_file = base_path / "data.json"
        assert not deleted_file.exists()

    @pytest.mark.asyncio
    async def test_delete_directory(self, test_structure):
        """Test deleting directory."""
        base_path = test_structure

        message = await delete_file_or_directory(base_path, "/worlds")

        assert "deleted successfully" in message

        # Verify directory was deleted
        deleted_dir = base_path / "worlds"
        assert not deleted_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, test_structure):
        """Test deleting nonexistent file."""
        base_path = test_structure

        with pytest.raises(HTTPException) as exc_info:
            await delete_file_or_directory(base_path, "/nonexistent.txt")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_rename_file(self, test_structure):
        """Test renaming file."""
        base_path = test_structure
        rename_request = RenameFileRequest(
            old_path="/config.txt", new_name="server_config.txt"
        )

        message = await rename_file_or_directory(base_path, rename_request)

        assert "renamed successfully" in message

        # Verify file was renamed
        old_file = base_path / "config.txt"
        new_file = base_path / "server_config.txt"
        assert not old_file.exists()
        assert new_file.exists()

    @pytest.mark.asyncio
    async def test_rename_directory(self, test_structure):
        """Test renaming directory."""
        base_path = test_structure
        rename_request = RenameFileRequest(old_path="/plugins", new_name="mods")

        message = await rename_file_or_directory(base_path, rename_request)

        assert "renamed successfully" in message

        # Verify directory was renamed
        old_dir = base_path / "plugins"
        new_dir = base_path / "mods"
        assert not old_dir.exists()
        assert new_dir.exists()
        assert new_dir.is_dir()

    @pytest.mark.asyncio
    async def test_rename_nonexistent(self, test_structure):
        """Test renaming nonexistent file."""
        base_path = test_structure
        rename_request = RenameFileRequest(
            old_path="/nonexistent.txt", new_name="new_name.txt"
        )

        with pytest.raises(HTTPException) as exc_info:
            await rename_file_or_directory(base_path, rename_request)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_rename_to_existing(self, test_structure):
        """Test renaming to existing name."""
        base_path = test_structure
        rename_request = RenameFileRequest(old_path="/config.txt", new_name="data.json")

        with pytest.raises(HTTPException) as exc_info:
            await rename_file_or_directory(base_path, rename_request)

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    def test_file_item_model(self):
        """Test FileItem model."""
        item = FileItem(
            name="test.txt",
            type="file",
            size=1024,
            modified_at=1640995200.0,  # 2022-01-01 00:00:00 UTC
            path="/test.txt",
        )

        assert item.name == "test.txt"
        assert item.type == "file"
        assert item.size == 1024
        assert item.path == "/test.txt"

    def test_file_list_response_model(self):
        """Test FileListResponse model."""
        items = [
            FileItem(
                name="file1.txt",
                type="file",
                size=100,
                modified_at=1640995200.0,
                path="/file1.txt",
            ),
            FileItem(
                name="dir1",
                type="directory",
                size=0,
                modified_at=1640995200.0,
                path="/dir1",
            ),
        ]
        response = FileListResponse(items=items, current_path="/")

        assert len(response.items) == 2
        assert response.current_path == "/"


if __name__ == "__main__":
    pytest.main([__file__])
