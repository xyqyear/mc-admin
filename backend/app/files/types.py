"""
File operation type definitions and Pydantic models.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Basic file models
class FileItem(BaseModel):
    name: str
    type: Literal["file", "directory"]
    size: int
    modified_at: float
    path: str


class FileListResponse(BaseModel):
    items: List[FileItem]
    current_path: str


class FileContent(BaseModel):
    content: str


class CreateFileRequest(BaseModel):
    name: str
    type: Literal["file", "directory"]
    path: str


class RenameFileRequest(BaseModel):
    old_path: str
    new_name: str


# Multi-file upload models
class FileStructureItem(BaseModel):
    """Represents a file or directory in the upload structure"""

    path: str  # Relative path within the upload structure
    name: str  # File or directory name
    type: Literal["file", "directory"]
    size: Optional[int] = None  # Size for files, None for directories


class MultiFileUploadRequest(BaseModel):
    """Request to check file structure before upload"""

    files: List[FileStructureItem]  # Files and directories to upload


class OverwriteConflict(BaseModel):
    """Information about a file that would be overwritten"""

    path: str  # Full path on server
    type: Literal["file", "directory"]
    current_size: Optional[int] = None  # Current file size if it's a file
    new_size: Optional[int] = None  # New file size if it's a file


class UploadConflictResponse(BaseModel):
    """Response with overwrite conflicts"""

    session_id: str  # Unique session ID for this upload
    conflicts: List[OverwriteConflict]  # Files that would be overwritten


class OverwriteDecision(BaseModel):
    """Overwrite decision for a specific file"""

    path: str
    overwrite: bool


class OverwritePolicy(BaseModel):
    """Policy for handling overwrite conflicts"""

    mode: Literal["always_overwrite", "never_overwrite", "per_file"]
    decisions: Optional[List[OverwriteDecision]] = (
        None  # Required when mode is "per_file"
    )


class UploadSession(BaseModel):
    """Upload session data stored in memory"""

    session_id: str
    conflicts: List[OverwriteConflict]
    policy: Optional[OverwritePolicy] = None
    expires_at: float  # Unix timestamp
    created_at: float  # Unix timestamp
    reusable: bool = False  # Whether session can be reused for multiple uploads


# Upload result models
class UploadFileResult(BaseModel):
    """Result for individual file upload"""

    status: Literal["success", "failed", "skipped"]
    reason: Optional[str] = (
        None  # Error message for failed, reason for skipped ("exists", "no_decision")
    )


class MultiFileUploadResult(BaseModel):
    """Results for multi-file upload operation"""

    message: str
    results: Dict[str, UploadFileResult]  # Key is file path, value is result


# File search models
class FileType(str, Enum):
    """File type enumeration for search results"""

    FILE = "file"
    DIRECTORY = "directory"
    OTHER = "other"


class SearchFileItem(BaseModel):
    """File item with search-specific information"""

    name: str
    path: str  # Relative path from base
    type: FileType
    size: int
    modified_at: datetime


class FileSearchRequest(BaseModel):
    """Request parameters for file search"""

    regex: str = Field(..., description="Regular expression pattern to search for")
    ignore_case: bool = Field(
        default=True, description="Whether to ignore case in regex matching"
    )
    search_subfolders: bool = Field(
        default=True, description="Whether to search in subfolders"
    )
    min_size: Optional[int] = Field(
        default=None, description="Minimum file size in bytes", ge=0
    )
    max_size: Optional[int] = Field(
        default=None, description="Maximum file size in bytes", ge=0
    )
    newer_than: Optional[datetime] = Field(
        default=None, description="Find files newer than this date"
    )
    older_than: Optional[datetime] = Field(
        default=None, description="Find files older than this date"
    )


class FileSearchResponse(BaseModel):
    """Response containing search results"""

    query: FileSearchRequest
    results: List[SearchFileItem]
    total_count: int
    search_path: str
