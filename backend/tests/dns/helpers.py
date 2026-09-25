"""Replace an accessor's result while retaining ordinary mock assertions."""

from contextlib import contextmanager
from unittest.mock import DEFAULT, MagicMock, patch


@contextmanager
def patch_accessor(target, value=DEFAULT):
    result = MagicMock() if value is DEFAULT else value
    with patch(target, return_value=result):
        yield result
