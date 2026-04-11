"""CRUD operations for DynamicConfig model."""

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DynamicConfig


async def get_all_configs(session: AsyncSession) -> Dict[str, DynamicConfig]:
    result = await session.execute(select(DynamicConfig))
    return {
        config.module_name: config for config in result.scalars().all()
    }


async def get_config_by_module(
    session: AsyncSession, module_name: str
) -> Optional[DynamicConfig]:
    result = await session.execute(
        select(DynamicConfig).where(DynamicConfig.module_name == module_name)
    )
    return result.scalar_one_or_none()


async def create_config(
    session: AsyncSession,
    *,
    module_name: str,
    config_data: dict,
    config_schema_version: str,
) -> DynamicConfig:
    db_config = DynamicConfig(
        module_name=module_name,
        config_data=config_data,
        config_schema_version=config_schema_version,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(db_config)
    return db_config


async def upsert_config(
    session: AsyncSession,
    module_name: str,
    config_data: dict,
    config_schema_version: str,
) -> None:
    db_config = await get_config_by_module(session, module_name)

    if db_config:
        db_config.config_data = config_data
        db_config.config_schema_version = config_schema_version
        db_config.updated_at = datetime.now(timezone.utc)
    else:
        await create_config(
            session,
            module_name=module_name,
            config_data=config_data,
            config_schema_version=config_schema_version,
        )

    await session.commit()
