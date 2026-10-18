from datetime import UTC, datetime
from types import SimpleNamespace

from app.self_check import tasks
from app.self_check.types import SelfCheckFindingResult, SelfCheckRunEvent


async def test_running_check_exposes_current_findings_without_a_final_result(monkeypatch):
    finding = SelfCheckFindingResult(
        check_id="one", category="系统", severity="warning", status="warning",
        title="检查项", message="需要处理", created_at=datetime.now(UTC),
    )

    async def events(**kwargs):
        yield SelfCheckRunEvent(type="check_started", run_id="run", trigger="manual", scope="full", check_id="one", total_checks=2)
        yield SelfCheckRunEvent(type="check_finished", run_id="run", trigger="manual", scope="full", check_id="one", total_checks=2, findings=[finding])
        yield SelfCheckRunEvent(type="check_started", run_id="run", trigger="manual", scope="full", check_id="two", total_checks=2)

    service = SimpleNamespace(iter_self_check_events=events, validate_check_id=lambda _: SimpleNamespace(title="检查项"))
    monkeypatch.setattr(tasks, "get_self_check_service", lambda: service)
    updates = [update async for update in tasks.self_check_task(1, None)]
    assert all(update.result is None for update in updates)
    assert updates[-1].progress == 50
    details = updates[-1].progress_details
    assert details is not None
    assert details["checking"] and details["check_id"] == "two"
    assert details["completed_checks"] == 1 and details["total_checks"] == 2
    assert details["findings"] == [finding.model_dump(mode="json")]
