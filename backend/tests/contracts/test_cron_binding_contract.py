from app.cron.api_models import CronJobResponse
from app.servers.restart_schedule import RestartScheduleRequest, RestartScheduleResponse


def test_cron_binding_and_registration_metadata_are_additive():
    schema = CronJobResponse.model_json_schema()
    assert set(schema["required"]) == {
        "cronjob_id", "identifier", "name", "cron", "params", "execution_count",
        "is_system", "status", "created_at", "updated_at",
    }
    original_properties = {
        "cronjob_id", "identifier", "name", "cron", "second", "params", "execution_count",
        "is_system", "status", "created_at", "updated_at",
    }
    additions = {
        "managed_server_generation": "integer", "managed_purpose": "string", "managed_binding_issue": "string",
    }
    assert set(schema["properties"]) == original_properties | additions.keys() | {"registration_status", "registration_error"}
    for name, kind in additions.items():
        assert schema["properties"][name]["anyOf"] == [{"type": kind}, {"type": "null"}]
        assert schema["properties"][name]["default"] is None
    assert set(RestartScheduleRequest.model_json_schema()["properties"]) == {"custom_cron"}
    response = RestartScheduleResponse.model_json_schema()
    assert set(response["properties"]) == {
        "cronjob_id", "server_id", "name", "cron", "status", "next_run_time", "scheduled_time",
        "registration_status", "registration_error",
    }
    assert set(response["required"]) == {
        "cronjob_id", "server_id", "name", "cron", "status", "scheduled_time",
    }
    for contract in (schema, response):
        registration = contract["properties"]["registration_status"]
        assert registration["enum"] == ["registered", "pending", "failed", "blocked", "inactive"]
        assert registration["type"] == "string" and registration["default"] == "pending"
        error = contract["properties"]["registration_error"]
        assert error["anyOf"] == [{"type": "string"}, {"type": "null"}]
        assert error["default"] is None
