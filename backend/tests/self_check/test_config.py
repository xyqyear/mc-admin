from app.dynamic_config.configs.self_check import (
    SelfCheckConfig,
    SelfCheckEnabledChecksConfig,
)
from app.self_check.constants import CHECK_IDS


def test_self_check_boolean_toggles_control_enabled_check_ids() -> None:
    config = SelfCheckConfig(
        checks=SelfCheckEnabledChecksConfig(
            dns_drift=False,
            backup_server_snapshot_freshness=False,
        )
    )

    enabled = config.enabled_check_ids()

    assert "dns.drift" not in enabled
    assert "backup.server_snapshot_freshness" not in enabled
    assert enabled == set(CHECK_IDS) - {
        "dns.drift",
        "backup.server_snapshot_freshness",
    }


def test_self_check_schema_exposes_boolean_check_toggles() -> None:
    schema = SelfCheckConfig.model_json_schema()
    checks_schema = schema["$defs"]["SelfCheckEnabledChecksConfig"]

    assert checks_schema["properties"]["dns_drift"]["type"] == "boolean"
    assert checks_schema["properties"]["dns_drift"]["title"] == "DNS 状态漂移"
    assert "enabled_checks" not in schema["properties"]


def test_self_check_backup_mod_ids_are_normalized() -> None:
    config = SelfCheckConfig(backup_mod_ids=["FTBBackups3", " DriveBackupV2 ", ""])

    assert config.backup_mod_ids == ["ftbbackups3", "drivebackupv2"]


def test_self_check_legacy_backup_name_patterns_use_default_ids() -> None:
    config = SelfCheckConfig.model_validate(
        {"backup_mod_name_patterns": ["ftbbackups", "simple-backups"]}
    )

    assert "ftbbackups" in config.backup_mod_ids
    assert "simplebackups" in config.backup_mod_ids
    assert "simple-backups" not in config.backup_mod_ids
