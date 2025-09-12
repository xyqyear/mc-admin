"""
Dynamic configuration system with type-safe access interface.

Usage:
    from app.dynamic_config import config

    # Access configuration with full type safety
    server_name = config.minecraft.server_name  # str
    max_memory = config.minecraft.resources.max_memory_mb  # int
    players = config.minecraft.players  # List[PlayerConfig]
"""

# Import all configuration schema classes
from .configs.dns import DNSManagerConfig
from .manager import config_manager
from .schemas import BaseConfigSchema


class ConfigProxy:
    """
    Proxy object providing type-safe access to dynamic configurations.

    This class uses __getattr__ to dynamically provide access to configuration
    modules registered with the ConfigManager. Each attribute access returns
    the actual configuration instance with full type safety.

    Example:
        config.minecraft returns MinecraftConfig instance
        config.backup returns BackupConfig instance
    """

    def __init__(self, manager=config_manager):
        """
        Initialize the configuration proxy.

        Args:
            manager: ConfigManager instance to use (allows dependency injection for testing)
        """
        self._manager = manager

    @property
    def dns(self):
        return getattr(self, "dns")

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


# Register all configuration modules
config_manager.register_config("dns", DNSManagerConfig)

# Global configuration proxy instance
# This is the main interface that application code should import and use
config = ConfigProxy()

# Re-export commonly used classes and functions
__all__ = [
    "config",
    "config_manager",
    "BaseConfigSchema",
    "ConfigProxy",
    "DNSManagerConfig",
]
