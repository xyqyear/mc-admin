from typing import Literal

from pydantic import BaseModel, Field


class FilePathsRequest(BaseModel):
    paths: list[str] = Field(min_length=1)


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


class PopulateServerRequest(BaseModel):
    archive_filename: str


class PopulateServerResponse(BaseModel):
    task_id: str
