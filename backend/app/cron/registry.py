"""
Cron job registry for registering and managing cron job functions.
"""

from typing import Dict, Optional, Type

from ..dynamic_config.schemas import BaseConfigSchema
from .jobs.backup import BackupJobParams, backup_cronjob
from .jobs.restart import ServerRestartParams, restart_server_cronjob
from .types import AsyncCronJobFunction, CronJobRegistration
from ..self_check.job import SelfCheckJobParams, self_check_cronjob


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
        is_system: bool = False,
        default_cron: Optional[str] = None,
        default_second: Optional[str] = None,
        default_params: Optional[BaseConfigSchema] = None,
        default_name: Optional[str] = None,
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
                server_id: str

            @cron_registry.register(
                schema_cls=ServerRestartParams,
                identifier="restart_server",
                description="Restart a Minecraft server"
            )
            async def restart_server_cronjob(context: ExecutionContext):
                server_id = context.params.server_id
                context.log(f"Restarting server: {server_id}")
                # Restart logic here...
            ```
        """

        def decorator(func: AsyncCronJobFunction) -> AsyncCronJobFunction:
            return self.register_func(
                func=func,
                schema_cls=schema_cls,
                identifier=identifier,
                description=description,
                is_system=is_system,
                default_cron=default_cron,
                default_second=default_second,
                default_params=default_params,
                default_name=default_name,
            )

        return decorator

    def register_func(
        self,
        func: AsyncCronJobFunction,
        schema_cls: Type[BaseConfigSchema],
        identifier: Optional[str] = None,
        description: str = "",
        is_system: bool = False,
        default_cron: Optional[str] = None,
        default_second: Optional[str] = None,
        default_params: Optional[BaseConfigSchema] = None,
        default_name: Optional[str] = None,
    ):
        """
        Register a cron job function.

        Args:
            func: The cron job function to register
            schema_cls: The Pydantic schema class for cron job parameters
            identifier: CronJob identifier (defaults to function name)
            description: Human-readable description of the cron job
        """
        cronjob_identifier = identifier or func.__name__
        self._cronjobs[cronjob_identifier] = CronJobRegistration(
            function=func,
            description=description,
            schema_cls=schema_cls,
            is_system=is_system,
            default_cron=default_cron,
            default_second=default_second,
            default_params=default_params,
            default_name=default_name,
        )

        return func

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


cron_registry.register_func(
    func=restart_server_cronjob,
    schema_cls=ServerRestartParams,
    identifier="restart_server",
    description="重启服务器",
)

cron_registry.register_func(
    func=backup_cronjob,
    schema_cls=BackupJobParams,
    identifier="backup",
    description="创建备份快照并清理旧快照",
)

cron_registry.register_func(
    func=self_check_cronjob,
    schema_cls=SelfCheckJobParams,
    identifier="self_check",
    description="自动运行系统自检",
    is_system=True,
    default_cron="0 * * * *",
    default_second="0",
    default_params=SelfCheckJobParams(),
    default_name="自动系统自检",
)
