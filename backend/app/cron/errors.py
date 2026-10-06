from ..errors import INTERNAL_ERROR_MESSAGE, PublicOperationError


def cron_value_error(message: str, *, public_message: str | None = None) -> ValueError:
    error = ValueError(message)
    vars(error)["cron_public_message"] = message if public_message is None else public_message
    return error


def cron_error_message(error: Exception) -> str:
    if isinstance(error, PublicOperationError):
        return str(error)
    message = vars(error).get("cron_public_message")
    return message if isinstance(message, str) else INTERNAL_ERROR_MESSAGE
