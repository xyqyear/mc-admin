from typing import Literal

from pydantic import BaseModel, Field


class FilePathsRequest(BaseModel):
    paths: list[str] = Field(min_length=1)


class DownloadManifestRequest(FilePathsRequest):
    cursor: str | None = None
    limit: int = Field(default=200, ge=1, le=500)


class DownloadManifestEntry(BaseModel):
    path: str
    type: Literal["file", "directory"]
    size: int


class DownloadManifestError(BaseModel):
    path: str
    message: str


class DownloadManifestResponse(BaseModel):
    server_generation: int
    entries: list[DownloadManifestEntry]
    errors: list[DownloadManifestError]
    next_cursor: str | None


class PopulateServerRequest(BaseModel):
    archive_filename: str


class PopulateServerResponse(BaseModel):
    task_id: str
