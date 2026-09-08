import zipfile
from pathlib import Path

import pytest

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


def test_extracts_quilt_loader_id_without_dependency_ids(tmp_path: Path) -> None:
    jar_path = tmp_path / "quilt.jar"
    write_jar(
        jar_path,
        {"quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "group": "invalid.e2e",
                "version": "1.0.0",
                "intermediate_mappings": "net.fabricmc:intermediary",
                "depends": [{"id": "unrelated_dependency", "versions": "*"}],
                "id": "ftbbackups2"
            }
        }'''},
    )

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ("ftbbackups2",)
    assert metadata.sources == ("quilt.mod.json",)


@pytest.mark.parametrize(
    "content",
    [
        '{"schema_version":1,"quilt_loader":{"depends":[{"id":"ftbbackups2"}],',
        ('{"schema_version":1,"quilt_loader":{"depends":[{"id":"ftbbackups2"}],'
        '"group":"invalid.e2e","id":"ordinary_mod","version":"1.0.0",}}'),
        ('{"schema_version":1,"quilt_loader":{"group":"invalid.e2e",'
        '"id":"ftbbackups2","version":"1.0.0",'
        '"metadata":{"description":"line one\nline two"}}}'),
    ],
    ids=["truncated-dependency-first", "trailing-comma-dependency-first", "literal-newline"],
)
def test_malformed_quilt_json_does_not_fall_back_to_any_id(
    tmp_path: Path, content: str
) -> None:
    jar_path = tmp_path / "malformed-quilt.jar"
    write_jar(jar_path, {"quilt.mod.json": content})

    metadata = extract_jar_metadata(jar_path)

    assert metadata.ids == ()
    assert metadata.sources == ("quilt.mod.json",)


@pytest.mark.parametrize("content", [
    '{"id":"root_is_not_quilt_id"}',
    '{"quilt_loader":null}',
    '{"quilt_loader":{"id":123}}',
    '{"quilt_loader":{"depends":[{"id":"ftbbackups2"}]}}',
])
def test_invalid_quilt_loader_does_not_invent_mod_ids(tmp_path: Path, content: str) -> None:
    jar_path = tmp_path / "invalid-quilt.jar"
    write_jar(jar_path, {"quilt.mod.json": content})

    assert extract_jar_metadata(jar_path).ids == ()


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
