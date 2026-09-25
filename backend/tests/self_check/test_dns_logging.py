from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from huaweicloudsdkcore.exceptions.exceptions import SdkException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from app.errors import INTERNAL_ERROR_MESSAGE
from app.self_check.checks import dns
from app.self_check.checks.base import SelfCheckContext, get_self_check_dependencies

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
    dependencies = get_self_check_dependencies()
    monkeypatch.setattr(dependencies, "configuration", SimpleNamespace(dns=SimpleNamespace(enabled=True)))
    monkeypatch.setattr(
        dependencies.connectivity,
        "observe",
        AsyncMock(side_effect=failure),
    )

    findings = await dns.check_dns_drift(SelfCheckContext(MagicMock(), SimpleNamespace()))

    assert len(findings) == 1
    assert findings[0].status == "warning"
    assert findings[0].evidence == {"error": INTERNAL_ERROR_MESSAGE}
    assert SECRET_DETAIL not in findings[0].model_dump_json()
    assert type(failure).__name__ in caplog.text
    assert SECRET_DETAIL not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_dns_programming_error_propagates_to_runner(monkeypatch, caplog):
    failure = LookupError(SECRET_DETAIL)
    dependencies = get_self_check_dependencies()
    monkeypatch.setattr(dependencies, "configuration", SimpleNamespace(dns=SimpleNamespace(enabled=True)))
    monkeypatch.setattr(
        dependencies.connectivity,
        "observe",
        AsyncMock(side_effect=failure),
    )

    with pytest.raises(LookupError) as caught:
        await dns.check_dns_drift(SelfCheckContext(MagicMock(), SimpleNamespace()))

    assert caught.value is failure
    assert SECRET_DETAIL not in caplog.text
