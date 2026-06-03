import os
import shutil
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

_CONFIG_PATH = os.getenv("MC_ADMIN_CONFIG", "config.toml")
_ENV_PATH = os.getenv("MC_ADMIN_ENV", ".env")
_BINARY_FALLBACK_DIRS = (Path("/usr/local/bin"), Path("/usr/bin"))


def _resolve_binary_default(binary_name: str) -> Path:
    resolved = shutil.which(binary_name)
    if resolved is not None:
        return Path(resolved)

    for directory in _BINARY_FALLBACK_DIRS:
        candidate = directory / binary_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    return Path(binary_name)


class JWTSettings(BaseModel):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"


class AuditSettings(BaseModel):
    enabled: bool = True
    log_file: str = "operations.log"
    log_request_body: bool = True
    max_body_size: int = 10240
    sensitive_fields: list[str] = ["password", "token", "secret", "key"]


class ResticSettings(BaseModel):
    repository_path: str
    password: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        toml_file=_CONFIG_PATH,
        env_file=_ENV_PATH,
    )

    static_path: Path = Field(default=Path("static"))

    cgroup_path: Path = Field(default=Path("/sys/fs/cgroup"))

    fd_binary_path: Path = Field(default_factory=lambda: _resolve_binary_default("fd"))
    mcmap_binary_path: Path = Field(
        default_factory=lambda: _resolve_binary_default("mcmap")
    )
    restic_binary_path: Path = Field(
        default_factory=lambda: _resolve_binary_default("restic")
    )

    database_url: str = Field(default="sqlite+aiosqlite:///./db.sqlite3")
    master_token: str
    jwt: JWTSettings
    audit: AuditSettings = Field(default_factory=AuditSettings)
    restic: Optional[ResticSettings] = None

    server_path: Path
    logs_dir: Path = Field(default=Path("logs"))
    archive_path: Path = Field(default=Path("archives"))

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()  # type: ignore
