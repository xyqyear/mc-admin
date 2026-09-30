from pathlib import Path

import pytest

from app.config import Settings

DIRECTORIES = {
    "static_path": "static",
    "cgroup_path": "cgroup",
    "server_path": "servers",
    "logs_dir": "logs",
    "archive_path": "archives",
}


@pytest.fixture(autouse=True)
def settings_sources(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    configuration = tmp_path / "configuration"
    configuration.mkdir()
    toml = configuration / "config.toml"
    dotenv = configuration / ".env"
    toml.write_text("")
    dotenv.write_text("")
    monkeypatch.setitem(Settings.model_config, "toml_file", toml)
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv)
    for field in DIRECTORIES:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setenv("SERVER_PATH", "servers")
    return toml, dotenv


def test_default_directories_are_bound_to_configuration_load_directory(monkeypatch, tmp_path):
    settings = Settings()  # type: ignore
    assert settings.server_path == tmp_path / "servers"
    assert settings.archive_path == tmp_path / "archives"
    assert settings.logs_dir == tmp_path / "logs"
    assert settings.static_path == tmp_path / "static"
    assert not settings.archive_path.exists()
    monkeypatch.chdir(tmp_path / "configuration")
    assert settings.archive_path == tmp_path / "archives"


@pytest.mark.parametrize("source", ["init", "toml", "dotenv", "environment"])
def test_directory_sources_resolve_from_working_directory(source, settings_sources, monkeypatch, tmp_path):
    values = {field: f"./data/../{name}" for field, name in DIRECTORIES.items()}
    monkeypatch.delenv("SERVER_PATH")
    if source == "toml":
        settings_sources[0].write_text("\n".join(f'{key} = "{value}"' for key, value in values.items()))
    elif source == "dotenv":
        settings_sources[1].write_text("\n".join(f"{key.upper()}={value}" for key, value in values.items()))
    elif source == "environment":
        for key, value in values.items():
            monkeypatch.setenv(key.upper(), value)
    settings = Settings(**(values if source == "init" else {}))  # type: ignore
    for field, name in DIRECTORIES.items():
        assert getattr(settings, field) == tmp_path / name


def test_absolute_directory_and_non_directory_settings_keep_their_meaning(tmp_path):
    archive = tmp_path / "absolute-archives"
    settings = Settings(  # type: ignore
        archive_path=archive,
        fd_binary_path=Path("fd"),
        mcmap_binary_path=Path("mcmap"),
        restic_binary_path=Path("restic"),
        database_url="sqlite+aiosqlite:///./db.sqlite3",
        restic={"repository_path": "sftp:backup:/repository"},
    )
    assert settings.archive_path == archive
    assert settings.fd_binary_path == Path("fd")
    assert settings.mcmap_binary_path == Path("mcmap")
    assert settings.restic_binary_path == Path("restic")
    assert settings.database_url == "sqlite+aiosqlite:///./db.sqlite3"
    assert settings.restic is not None
    assert settings.restic.repository_path == "sftp:backup:/repository"


def test_directory_symlinks_resolve_to_the_same_root(tmp_path):
    target = tmp_path / "storage"
    target.mkdir()
    (tmp_path / "archives-link").symlink_to(target, target_is_directory=True)
    settings = Settings(archive_path=Path("archives-link"))  # type: ignore
    assert settings.archive_path == target
