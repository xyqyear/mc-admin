def normalize_uuid(value: str) -> str | None:
    normalized = value.replace("-", "").lower()
    if len(normalized) != 32 or any(char not in "0123456789abcdef" for char in normalized):
        return None
    return normalized
