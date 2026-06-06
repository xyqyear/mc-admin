import zipfile
from pathlib import Path

from app.self_check.checks.server import find_backup_jars_sync


def write_jar(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as jar:
        for name, content in files.items():
            jar.writestr(name, content)


def test_backup_mod_scan_uses_metadata_ids_for_renamed_mods(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    write_jar(
        mods_dir / "totally-renamed.jar",
        {"META-INF/mods.toml": '[[mods]]\nmodId = "ftbbackups"\n'},
    )
    write_jar(
        mods_dir / "looks-like-backup-but-is-not.jar",
        {"fabric.mod.json": '{"schemaVersion":1,"id":"notbackup"}'},
    )

    matches = find_backup_jars_sync(tmp_path, ["ftbbackups"])

    assert len(matches) == 1
    assert matches[0].directory == "mods"
    assert matches[0].file == "totally-renamed.jar"
    assert matches[0].ids == ["ftbbackups"]


def test_backup_mod_scan_checks_plugins_directory(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    write_jar(
        plugins_dir / "renamed-plugin.jar",
        {"plugin.yml": "name: ServerBackup\nmain: net.server_backup.ServerBackup\n"},
    )

    matches = find_backup_jars_sync(tmp_path, ["serverbackup"])

    assert len(matches) == 1
    assert matches[0].directory == "plugins"
    assert matches[0].ids == ["serverbackup"]
    assert matches[0].sources == ["plugin.yml"]


def test_backup_mod_scan_ignores_invalid_jars(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    (mods_dir / "ftbbackups.jar").write_bytes(b"not a jar")

    matches = find_backup_jars_sync(tmp_path, ["ftbbackups"])

    assert matches == []
