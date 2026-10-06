import pytest
from pydantic import ValidationError

from app.files.api_models import DownloadManifestRequest, FilePathsRequest


def test_file_batch_requests_require_a_nonempty_selection() -> None:
    for request_type in (FilePathsRequest, DownloadManifestRequest):
        with pytest.raises(ValidationError):
            request_type.model_validate({"paths": []})


@pytest.mark.parametrize("limit", [0, 501])
def test_download_manifest_rejects_limits_outside_the_bounded_page(limit: int) -> None:
    with pytest.raises(ValidationError):
        DownloadManifestRequest(paths=["world"], limit=limit)


@pytest.mark.parametrize("limit", [1, 500])
def test_download_manifest_accepts_both_page_boundaries(limit: int) -> None:
    request = DownloadManifestRequest(paths=["world"], limit=limit)
    assert request.limit == limit
    assert request.cursor is None


def test_download_manifest_defaults_to_a_bounded_initial_page() -> None:
    request = DownloadManifestRequest(paths=["world"])
    assert request.limit == 200
    assert request.cursor is None
