"""
File operations module with organized components.

This module provides file management capabilities including:
- Basic file operations (CRUD, listing)
- Multi-file upload with conflict detection
- Session-based upload management
- Type definitions for all operations
"""

# Type exports
# Base file operations
from .base import (
    create_file_or_directory,
    delete_file_or_directory,
    get_file_content,
    get_file_items,
    rename_file_or_directory,
    update_file_content,
)

# Multi-file operations
from .multi_file import (
    check_upload_conflicts,
    set_upload_policy,
    upload_multiple_files,
)
from .ownership import restore_tree_ownership_task
from .search import search_files
from .types import (
    CreateFileRequest,
    FileContent,
    FileItem,
    FileListResponse,
    FileSearchRequest,
    FileSearchResponse,
    FileStructureItem,
    FileType,
    MultiFileUploadRequest,
    MultiFileUploadResult,
    OverwriteConflict,
    OverwriteDecision,
    OverwritePolicy,
    OwnershipRestoreTaskResponse,
    RenameFileRequest,
    SearchFileItem,
    UploadConflictResponse,
    UploadFileResult,
    UploadSession,
)

# Utilities
# Internal utilities for testing
from .utils import (
    _SESSION_TIMEOUT,
    _upload_sessions,
    get_upload_session,
)

__all__ = [
    # Internal utilities for testing
    "_SESSION_TIMEOUT",
    # Types
    "CreateFileRequest",
    "FileContent",
    "FileItem",
    "FileListResponse",
    "FileSearchRequest",
    "FileSearchResponse",
    "FileStructureItem",
    "FileType",
    "MultiFileUploadRequest",
    "MultiFileUploadResult",
    "OverwriteConflict",
    "OverwriteDecision",
    "OverwritePolicy",
    "OwnershipRestoreTaskResponse",
    "RenameFileRequest",
    "SearchFileItem",
    "UploadConflictResponse",
    "UploadFileResult",
    "UploadSession",
    "_upload_sessions",
    # Multi-file operations
    "check_upload_conflicts",
    # Base operations
    "create_file_or_directory",
    "delete_file_or_directory",
    "get_file_content",
    "get_file_items",
    # Utilities
    "get_upload_session",
    "rename_file_or_directory",
    "restore_tree_ownership_task",
    "search_files",
    "set_upload_policy",
    "update_file_content",
    "upload_multiple_files",
]
