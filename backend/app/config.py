import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

_CONFIG_PATH = os.getenv("MC_ADMIN_CONFIG", "config.toml")
_ENV_PATH = os.getenv("MC_ADMIN_ENV", ".env")


class JWTSettings(BaseModel):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30


class AuditSettings(BaseModel):
    enabled: bool = True
    log_file: str = "operations.log"
    log_request_body: bool = True
    max_body_size: int = 10240  # 10KB
    sensitive_fields: list[str] = ["password", "token", "secret", "key"]


class ResticSettings(BaseModel):
    repository_path: str
    password: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        toml_file=_CONFIG_PATH,
        env_file=_ENV_PATH,
    )

    database_url: str
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
        # Source order: init args > OS env > .env > config.toml > secrets
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()  # type: ignore We want the app to fail if the settings are not loaded correctly
