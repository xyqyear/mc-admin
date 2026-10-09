import pytest
from pydantic import ValidationError

from app.files.api_models import FilePathsRequest


def test_file_batch_requests_require_a_nonempty_selection() -> None:
    with pytest.raises(ValidationError):
        FilePathsRequest.model_validate({"paths": []})
