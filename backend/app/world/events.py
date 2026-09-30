from ..errors import PublicOperationError


class RestoreError(PublicOperationError):
    pass


class SelectionResolutionError(RestoreError):
    """Raised when a selection cannot be resolved to filesystem paths."""
