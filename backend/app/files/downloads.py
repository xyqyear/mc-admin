"""Complete recursive file manifests for browser-owned local exports."""

from typing import Literal, cast

from ..servers.references import ServerRef
from ..utils import async_fs
from .api_models import (
    DownloadManifestEntry,
    DownloadManifestError,
    DownloadManifestResponse,
    FilePathsRequest,
)
from .paths import normalize_selected_paths


async def download_manifest(reference: ServerRef, request: FilePathsRequest) -> DownloadManifestResponse:
    roots = await normalize_selected_paths(reference.data_path, request.paths)
    entries = await async_fs.tree_entries(reference.data_path, roots)
    return DownloadManifestResponse(
        server_generation=reference.generation,
        entries=[DownloadManifestEntry(path=path, type=cast(Literal["file", "directory"], kind), size=size) for path, kind, size, error in entries if error is None],
        errors=[DownloadManifestError(path=path, message=error) for path, _, _, error in entries if error is not None],
    )
