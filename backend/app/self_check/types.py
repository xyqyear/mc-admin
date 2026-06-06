"""Pydantic models used by self-check execution and API responses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SelfCheckSeverity = Literal["success", "info", "warning", "critical"]
SelfCheckFindingStatus = Literal[
    "passed", "info", "warning", "critical", "skipped", "failed"
]
SelfCheckRunStatus = Literal["success", "warning", "critical"]
SelfCheckRunScope = Literal["full", "check"]
SelfCheckRunEventType = Literal[
    "started", "check_started", "check_finished", "completed", "error"
]


class SelfCheckFindingResult(BaseModel):
    check_id: str
    category: str
    severity: SelfCheckSeverity
    status: SelfCheckFindingStatus
    title: str
    message: str
    server_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    remediation: list[str] = Field(default_factory=list)
    created_at: datetime

    @property
    def is_problem(self) -> bool:
        return self.severity in ("warning", "critical")


class SelfCheckSummary(BaseModel):
    total: int
    passed: int
    skipped: int
    info: int
    warning: int
    critical: int
    failed: int
    status: SelfCheckRunStatus


class SelfCheckRunResult(BaseModel):
    id: str
    trigger: str
    scope: SelfCheckRunScope = "full"
    check_id: str | None = None
    status: SelfCheckRunStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    summary: SelfCheckSummary
    findings: list[SelfCheckFindingResult]
    error_message: str | None = None


class SelfCheckCatalogItem(BaseModel):
    check_id: str
    category: str
    title: str
    description: str
    enabled: bool


class SelfCheckRunSummaryRecord(BaseModel):
    id: str
    trigger: str
    scope: SelfCheckRunScope
    check_id: str | None
    status: SelfCheckRunStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    summary: SelfCheckSummary
    requested_by_user_id: int | None
    error_message: str | None


class SelfCheckRunDetail(SelfCheckRunSummaryRecord):
    findings: list[SelfCheckFindingResult]


class SelfCheckCurrentState(BaseModel):
    status: SelfCheckRunStatus
    updated_at: datetime
    source_run_id: str
    summary: SelfCheckSummary
    findings: list[SelfCheckFindingResult]


class SelfCheckRunsResponse(BaseModel):
    runs: list[SelfCheckRunSummaryRecord]
    total: int


class SelfCheckRunEvent(BaseModel):
    type: SelfCheckRunEventType
    run_id: str
    trigger: str
    scope: SelfCheckRunScope
    check_id: str | None = None
    total_checks: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    findings: list[SelfCheckFindingResult] | None = None
    result: SelfCheckRunResult | None = None
    message: str | None = None
