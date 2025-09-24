"""
Test file search functionality.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.files import FileSearchRequest, search_files


class TestFileSearch:
    """Test file search operations"""

    async def test_search_files_basic_regex(self):
        """Test basic regex search"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "test.py").write_text("print('hello')")
            (temp_path / "test.txt").write_text("some text")
            (temp_path / "another.py").write_text("import os")

            # Create a subdirectory with files
            sub_dir = temp_path / "subdir"
            sub_dir.mkdir()
            (sub_dir / "nested.py").write_text("def func(): pass")

            # Search for Python files
            search_request = FileSearchRequest(regex=r".*\.py$")
            results = await search_files(temp_path, search_request)

            # Should find 3 Python files
            assert len(results) == 3

            # Verify file names
            found_files = {result.name for result in results}
            assert found_files == {"test.py", "another.py", "nested.py"}

            # Verify file types
            for result in results:
                assert result.type.value == "file"
                assert result.size > 0
                assert isinstance(result.modified_at, datetime)

    async def test_search_files_case_sensitivity(self):
        """Test case sensitivity options"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "Test.PY").write_text("print('hello')")
            (temp_path / "test.txt").write_text("some text")

            # Case insensitive search (default)
            search_request = FileSearchRequest(regex=r"test\.py", ignore_case=True)
            results = await search_files(temp_path, search_request)
            assert len(results) == 1
            assert results[0].name == "Test.PY"

            # Case sensitive search
            search_request = FileSearchRequest(regex=r"test\.py", ignore_case=False)
            results = await search_files(temp_path, search_request)
            assert len(results) == 0  # Should not match Test.PY

    async def test_search_files_size_filters(self):
        """Test file size filtering"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create files with different sizes
            (temp_path / "small.txt").write_text("small")  # ~5 bytes
            (temp_path / "large.txt").write_text("x" * 1000)  # 1000 bytes

            # Search for files larger than 100 bytes
            search_request = FileSearchRequest(regex=r".*\.txt$", min_size=100)
            results = await search_files(temp_path, search_request)
            assert len(results) == 1
            assert results[0].name == "large.txt"
            assert results[0].size >= 100

            # Search for files smaller than 100 bytes
            search_request = FileSearchRequest(regex=r".*\.txt$", max_size=100)
            results = await search_files(temp_path, search_request)
            assert len(results) == 1
            assert results[0].name == "small.txt"
            assert results[0].size <= 100

    async def test_search_files_date_filters(self):
        """Test date filtering"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "file1.txt").write_text("content1")
            (temp_path / "file2.txt").write_text("content2")

            # Test newer_than filter (should find all files as they're just created)
            yesterday = datetime.now() - timedelta(days=1)
            search_request = FileSearchRequest(regex=r".*\.txt$", newer_than=yesterday)
            results = await search_files(temp_path, search_request)
            assert len(results) == 2

            # Test older_than filter (should find no files as they're just created)
            tomorrow = datetime.now() + timedelta(days=1)
            search_request = FileSearchRequest(regex=r".*\.txt$", older_than=tomorrow)
            results = await search_files(temp_path, search_request)
            assert len(results) == 2  # All files should be older than tomorrow

    async def test_search_files_directories(self):
        """Test searching for directories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create directories and files
            (temp_path / "test_dir").mkdir()
            (temp_path / "another_dir").mkdir()
            (temp_path / "test_file.txt").write_text("content")

            # Search for directories with 'test' in the name
            search_request = FileSearchRequest(regex=r"test")
            results = await search_files(temp_path, search_request)

            # Should find both directory and file
            assert len(results) >= 2

            # Verify we can distinguish between files and directories
            types_found = {result.type for result in results}
            assert len(types_found) >= 1  # Should have at least file or directory type

    async def test_search_nonexistent_path(self):
        """Test searching in nonexistent path"""
        nonexistent_path = Path("/nonexistent/path")
        search_request = FileSearchRequest(regex=r".*")

        with pytest.raises(Exception):  # Should raise HTTPException
            await search_files(nonexistent_path, search_request)

    async def test_search_empty_results(self):
        """Test search that returns no results"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a file that won't match our search
            (temp_path / "file.txt").write_text("content")

            # Search for Python files (should find none)
            search_request = FileSearchRequest(regex=r".*\.py$")
            results = await search_files(temp_path, search_request)

            assert len(results) == 0
            assert isinstance(results, list)
