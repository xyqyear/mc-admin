"""
Cron job registry for registering and managing cron job functions.
"""

from typing import Dict, Optional, Type

from ..dynamic_config.schemas import BaseConfigSchema
from .types import AsyncCronJobFunction, CronJobRegistration


class CronRegistry:
    """
    Registry for cron job functions with their metadata.

    This registry stores cron job functions along with their parameter schema
    classes and descriptions, enabling type-safe parameter handling.
    """

    def __init__(self):
        # identifier -> CronJobRegistration
        self._cronjobs: Dict[str, CronJobRegistration] = {}

    def register(
        self,
        schema_cls: Type[BaseConfigSchema],
        identifier: Optional[str] = None,
        description: str = "",
    ):
        """
        Decorator to register a cron job function.

        Args:
            schema_cls: The Pydantic schema class for cron job parameters
            identifier: CronJob identifier (defaults to function name)
            description: Human-readable description of the cron job

        Returns:
            Decorated cron job function

        Example:
            ```python
            class ServerRestartParams(BaseConfigSchema):
                server_name: str
                force: bool = False

            @cron_registry.register(
                schema_cls=ServerRestartParams,
                identifier="restart_server",
                description="Restart a Minecraft server"
            )
            async def restart_server_cronjob(context: ExecutionContext):
                server_name = context.params.server_name
                context.log(f"Restarting server: {server_name}")
                # Restart logic here...
            ```
        """

        def decorator(func: AsyncCronJobFunction) -> AsyncCronJobFunction:
            cronjob_identifier = identifier or func.__name__
            self._cronjobs[cronjob_identifier] = CronJobRegistration(
                function=func, description=description, schema_cls=schema_cls
            )
            return func

        return decorator

    def get_cronjob(self, identifier: str) -> Optional[CronJobRegistration]:
        """
        Get a registered cron job by identifier.

        Args:
            identifier: CronJob identifier

        Returns:
            CronJobRegistration or None if not found
        """
        return self._cronjobs.get(identifier)

    def get_all_cronjobs(
        self,
    ) -> Dict[str, CronJobRegistration]:
        """
        Get all registered cron jobs.

        Returns:
            Dictionary mapping identifiers to cron job metadata
        """
        return self._cronjobs.copy()

    def is_registered(self, identifier: str) -> bool:
        """
        Check if a cron job is registered.

        Args:
            identifier: CronJob identifier

        Returns:
            True if the cron job is registered
        """
        return identifier in self._cronjobs

    def get_schema_class(self, identifier: str) -> Optional[Type[BaseConfigSchema]]:
        """
        Get the parameter schema class for a cron job.

        Args:
            identifier: CronJob identifier

        Returns:
            Schema class or None if cron job not found
        """
        cronjob_registration = self._cronjobs.get(identifier)
        return cronjob_registration.schema_cls if cronjob_registration else None


# Global cron registry instance
cron_registry = CronRegistry()
