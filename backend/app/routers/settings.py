from typing import cast

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user
from ..dynamic_config.configs.dns import DNSManagerConfig
from ..dynamic_config.configs.log_parser import LogParserConfig
from ..dynamic_config.configs.mcmap import MCMapConfig
from ..dynamic_config.configs.players import PlayersConfig
from ..dynamic_config.configs.self_check import SelfCheckConfig
from ..dynamic_config.configs.snapshots import SnapshotsConfig
from ..dynamic_config.configs.world import WorldConfig
from ..dynamic_config.manager import get_config_manager
from ..dynamic_config.requests import (
    DNSSettingsUpdate,
    LogParserSettingsUpdate,
    MapSettingsUpdate,
    PlayerSettingsUpdate,
    SelfCheckSettingsUpdate,
    SnapshotSettingsUpdate,
    WorldSettingsUpdate,
)
from ..dynamic_config.schemas import BaseConfigSchema

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(get_current_user)])


async def _replace(module: str, settings: BaseConfigSchema) -> BaseConfigSchema:
    try:
        return await get_config_manager().update_config(module, settings.model_dump())
    except ValueError:
        raise HTTPException(status_code=400, detail="配置无效，请检查字段取值和业务约束") from None


@router.get("/dns", response_model=DNSManagerConfig)
async def get_dns_settings():
    return get_config_manager().get_config("dns")


@router.put("/dns", response_model=DNSManagerConfig)
async def replace_dns_settings(settings: DNSSettingsUpdate):
    return cast(DNSManagerConfig, await _replace("dns", settings))


@router.post("/dns/reset", response_model=DNSManagerConfig)
async def reset_dns_settings():
    return await get_config_manager().reset_config("dns")


@router.get("/snapshots", response_model=SnapshotsConfig)
async def get_snapshot_settings():
    return get_config_manager().get_config("snapshots")


@router.put("/snapshots", response_model=SnapshotsConfig)
async def replace_snapshot_settings(settings: SnapshotSettingsUpdate):
    return cast(SnapshotsConfig, await _replace("snapshots", settings))


@router.post("/snapshots/reset", response_model=SnapshotsConfig)
async def reset_snapshot_settings():
    return await get_config_manager().reset_config("snapshots")


@router.get("/log-parser", response_model=LogParserConfig)
async def get_log_parser_settings():
    return get_config_manager().get_config("log_parser")


@router.put("/log-parser", response_model=LogParserConfig)
async def replace_log_parser_settings(settings: LogParserSettingsUpdate):
    return cast(LogParserConfig, await _replace("log_parser", settings))


@router.post("/log-parser/reset", response_model=LogParserConfig)
async def reset_log_parser_settings():
    return await get_config_manager().reset_config("log_parser")


@router.get("/players", response_model=PlayersConfig)
async def get_player_settings():
    return get_config_manager().get_config("players")


@router.put("/players", response_model=PlayersConfig)
async def replace_player_settings(settings: PlayerSettingsUpdate):
    return cast(PlayersConfig, await _replace("players", settings))


@router.post("/players/reset", response_model=PlayersConfig)
async def reset_player_settings():
    return await get_config_manager().reset_config("players")


@router.get("/mcmap", response_model=MCMapConfig)
async def get_map_settings():
    return get_config_manager().get_config("mcmap")


@router.put("/mcmap", response_model=MCMapConfig)
async def replace_map_settings(settings: MapSettingsUpdate):
    return cast(MCMapConfig, await _replace("mcmap", settings))


@router.post("/mcmap/reset", response_model=MCMapConfig)
async def reset_map_settings():
    return await get_config_manager().reset_config("mcmap")


@router.get("/world", response_model=WorldConfig)
async def get_world_settings():
    return get_config_manager().get_config("world")


@router.put("/world", response_model=WorldConfig)
async def replace_world_settings(settings: WorldSettingsUpdate):
    return cast(WorldConfig, await _replace("world", settings))


@router.post("/world/reset", response_model=WorldConfig)
async def reset_world_settings():
    return await get_config_manager().reset_config("world")


@router.get("/self-check", response_model=SelfCheckConfig)
async def get_self_check_settings():
    return get_config_manager().get_config("self_check")


@router.put("/self-check", response_model=SelfCheckConfig)
async def replace_self_check_settings(settings: SelfCheckSettingsUpdate):
    return cast(SelfCheckConfig, await _replace("self_check", settings))


@router.post("/self-check/reset", response_model=SelfCheckConfig)
async def reset_self_check_settings():
    return await get_config_manager().reset_config("self_check")
