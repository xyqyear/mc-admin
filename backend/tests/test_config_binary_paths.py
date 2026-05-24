from pathlib import Path

from app import config


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)


def test_binary_default_uses_path(monkeypatch, tmp_path):
    binary = tmp_path / "path-bin" / "fd"
    _write_executable(binary)
    monkeypatch.setattr(
        config.shutil,
        "which",
        lambda name: str(binary) if name == "fd" else None,
    )

    assert config._resolve_binary_default("fd") == binary


def test_binary_default_falls_back_to_usr_local_before_usr(monkeypatch, tmp_path):
    usr_local = tmp_path / "usr-local-bin"
    usr = tmp_path / "usr-bin"
    usr_local_binary = usr_local / "mcmap"
    usr_binary = usr / "mcmap"
    _write_executable(usr_local_binary)
    _write_executable(usr_binary)
    monkeypatch.setattr(config.shutil, "which", lambda _: None)
    monkeypatch.setattr(config, "_BINARY_FALLBACK_DIRS", (usr_local, usr))

    assert config._resolve_binary_default("mcmap") == usr_local_binary


def test_binary_default_falls_back_to_usr(monkeypatch, tmp_path):
    usr_local = tmp_path / "usr-local-bin"
    usr = tmp_path / "usr-bin"
    usr_binary = usr / "restic"
    _write_executable(usr_binary)
    monkeypatch.setattr(config.shutil, "which", lambda _: None)
    monkeypatch.setattr(config, "_BINARY_FALLBACK_DIRS", (usr_local, usr))

    assert config._resolve_binary_default("restic") == usr_binary


def test_binary_default_returns_name_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config.shutil, "which", lambda _: None)
    monkeypatch.setattr(config, "_BINARY_FALLBACK_DIRS", (tmp_path / "bin",))

    assert config._resolve_binary_default("fd") == Path("fd")


def test_settings_configured_binary_paths_win(tmp_path):
    settings = config.Settings(
        master_token="token",
        jwt=config.JWTSettings(secret_key="secret"),
        server_path=tmp_path,
        fd_binary_path=Path("/custom/fd"),
        mcmap_binary_path=Path("/custom/mcmap"),
        restic_binary_path=Path("/custom/restic"),
    )

    assert settings.fd_binary_path == Path("/custom/fd")
    assert settings.mcmap_binary_path == Path("/custom/mcmap")
    assert settings.restic_binary_path == Path("/custom/restic")
