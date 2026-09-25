"""Typed configuration views bound to their owning manager."""

from typing import cast

from .configs.dns import DNSManagerConfig
from .configs.log_parser import LogParserConfig
from .configs.mcmap import MCMapConfig
from .configs.players import PlayersConfig
from .configs.self_check import SelfCheckConfig
from .configs.snapshots import SnapshotsConfig
from .configs.world import WorldConfig
from .manager import ConfigManager, get_config_manager
from .schemas import BaseConfigSchema


class ConfigProxy:
    """Resolve current cached values without changing the owning manager."""

    def __init__(self, manager: ConfigManager | None = None):
        self._manager = manager if manager is not None else get_config_manager()

    @property
    def dns(self):
        return cast(DNSManagerConfig, self._manager.get_config("dns"))

    @property
    def snapshots(self):
        return cast(SnapshotsConfig, self._manager.get_config("snapshots"))

    @property
    def log_parser(self):
        return cast(LogParserConfig, self._manager.get_config("log_parser"))

    @property
    def players(self):
        return cast(PlayersConfig, self._manager.get_config("players"))

    @property
    def mcmap(self):
        return cast(MCMapConfig, self._manager.get_config("mcmap"))

    @property
    def world(self):
        return cast(WorldConfig, self._manager.get_config("world"))

    @property
    def self_check(self):
        return cast(SelfCheckConfig, self._manager.get_config("self_check"))

    def __getattr__(self, module_name: str):
        """
        Get configuration instance for the specified module.

        Args:
            module_name: Name of the configuration module

        Returns:
            Configuration instance with full type safety

        Raises:
            AttributeError: If module not found or not registered
        """
        try:
            return self._manager.get_config(module_name)
        except (ValueError, RuntimeError) as e:
            raise AttributeError(
                f"Configuration module '{module_name}' not available: {e}"
            )


def get_config() -> ConfigProxy:
    from ..runtime_resources import current_runtime

    return current_runtime().resource("dynamic_configuration")

__all__ = [
    "BaseConfigSchema",
    "ConfigProxy",
    "DNSManagerConfig",
    "LogParserConfig",
    "MCMapConfig",
    "PlayersConfig",
    "SelfCheckConfig",
    "SnapshotsConfig",
    "WorldConfig",
    'get_config',
    'get_config_manager',
]
