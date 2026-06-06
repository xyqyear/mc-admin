import zipfile
from pathlib import Path

from app.self_check.jar_metadata import extract_jar_metadata


def write_jar(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as jar:
        for name, content in files.items():
            jar.writestr(name, content)


def test_extracts_fabric_mod_id(tmp_path: Path) -> None:
    jar_path = tmp_path / "renamed.jar"
    write_jar(
        jar_path,
        {"fabric.mod.json": '{"schemaVersion":1,"id":"ftbbackups3"}'},
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("ftbbackups3",)
    assert metadata.sources == ("fabric.mod.json",)


def test_extracts_fabric_id_from_lenient_json(tmp_path: Path) -> None:
    jar_path = tmp_path / "advanced.jar"
    write_jar(
        jar_path,
        {
            "fabric.mod.json": (
                '{\n'
                '  "id": "advancedbackups",\n'
                '  "description": "line one\nline two"\n'
                "}"
            )
        },
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("advancedbackups",)


def test_extracts_neoforge_mod_ids(tmp_path: Path) -> None:
    jar_path = tmp_path / "backup.jar"
    write_jar(
        jar_path,
        {
            "META-INF/neoforge.mods.toml": """
                [[mods]]
                modId = "simplebackups"

                [[mods]]
                modId = "backupmanager"
            """
        },
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("simplebackups", "backupmanager")
    assert metadata.sources == ("META-INF/neoforge.mods.toml",)


def test_extracts_legacy_mcmod_info_ids(tmp_path: Path) -> None:
    jar_path = tmp_path / "aroma.jar"
    write_jar(
        jar_path,
        {
            "mcmod.info": """
                [
                  {"modid": "aromabackup"},
                  {"modid": "aromabackuprecovery"}
                ]
            """
        },
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("aromabackup", "aromabackuprecovery")


def test_extracts_bukkit_plugin_name(tmp_path: Path) -> None:
    jar_path = tmp_path / "plugin.jar"
    write_jar(
        jar_path,
        {"plugin.yml": "name: DriveBackupV2\nmain: ratismal.drivebackup.plugin.DriveBackup\n"},
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("drivebackupv2",)
    assert metadata.sources == ("plugin.yml",)


def test_invalid_jar_returns_empty_metadata(tmp_path: Path) -> None:
    jar_path = tmp_path / "invalid.jar"
    jar_path.write_bytes(b"not a jar")

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ()
    assert metadata.sources == ()
