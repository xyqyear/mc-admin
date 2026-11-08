from pydantic import BaseModel, ConfigDict

from .configs.dns import DNSManagerConfig
from .configs.log_parser import LogParserConfig
from .configs.mcmap import MCMapConfig
from .configs.players import PlayersConfig
from .configs.self_check import SelfCheckConfig
from .configs.snapshots import SnapshotsConfig
from .configs.world import WorldConfig


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class DNSSettingsUpdate(DNSManagerConfig, SettingsUpdate):
    pass


class SnapshotSettingsUpdate(SnapshotsConfig, SettingsUpdate):
    pass


class LogParserSettingsUpdate(LogParserConfig, SettingsUpdate):
    pass


class PlayerSettingsUpdate(PlayersConfig, SettingsUpdate):
    pass


class MapSettingsUpdate(MCMapConfig, SettingsUpdate):
    pass


class WorldSettingsUpdate(WorldConfig, SettingsUpdate):
    pass


class SelfCheckSettingsUpdate(SelfCheckConfig, SettingsUpdate):
    pass
