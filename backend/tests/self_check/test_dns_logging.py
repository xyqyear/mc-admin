from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from huaweicloudsdkcore.exceptions.exceptions import SdkException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from app.self_check.checks import dns
from app.self_check.checks.base import SelfCheckContext

SECRET_DETAIL = "test-cloud-credential-error-detail"


@pytest.mark.parametrize(
    "failure",
    [
        SdkException(SECRET_DETAIL),
        TencentCloudSDKException("AuthFailure", SECRET_DETAIL),
        httpx2.HTTPError(SECRET_DETAIL),
        ValueError(SECRET_DETAIL),
        RuntimeError(SECRET_DETAIL),
        OSError(SECRET_DETAIL),
    ],
)
async def test_dns_failure_preserves_finding_without_logging_secret_details(
    failure, monkeypatch, caplog
):
    monkeypatch.setattr(dns, "config", SimpleNamespace(dns=SimpleNamespace(enabled=True)))
    monkeypatch.setattr(
        dns.simple_dns_manager,
        "get_current_diff",
        AsyncMock(side_effect=failure),
    )

    findings = await dns.check_dns_drift(SelfCheckContext(MagicMock(), SimpleNamespace()))

    assert len(findings) == 1
    assert findings[0].status == "warning"
    assert findings[0].evidence == {"error": str(failure)}
    assert type(failure).__name__ in caplog.text
    assert SECRET_DETAIL not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_dns_programming_error_propagates_to_runner(monkeypatch, caplog):
    failure = LookupError(SECRET_DETAIL)
    monkeypatch.setattr(dns, "config", SimpleNamespace(dns=SimpleNamespace(enabled=True)))
    monkeypatch.setattr(
        dns.simple_dns_manager,
        "get_current_diff",
        AsyncMock(side_effect=failure),
    )

    with pytest.raises(LookupError) as caught:
        await dns.check_dns_drift(SelfCheckContext(MagicMock(), SimpleNamespace()))

    assert caught.value is failure
    assert SECRET_DETAIL not in caplog.text
