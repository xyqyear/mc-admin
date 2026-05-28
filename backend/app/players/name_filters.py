"""Player name filters driven by dynamic configuration."""

from ..dynamic_config import config


def _ignored_prefixes() -> tuple[str, ...]:
    try:
        prefixes = config.players.ignored_name_prefixes
    except (RuntimeError, ValueError):
        return ()

    return tuple(prefix.strip().casefold() for prefix in prefixes if prefix.strip())


def is_ignored_player_name(player_name: str) -> bool:
    """Return whether ``player_name`` is excluded from player write paths."""
    normalized_name = player_name.casefold()
    return any(normalized_name.startswith(prefix) for prefix in _ignored_prefixes())
