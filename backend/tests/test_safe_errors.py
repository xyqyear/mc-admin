import logging

import pytest
from fastapi import FastAPI, HTTPException
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.database import get_engine
from app.errors import SafeErrorMiddleware


@pytest.mark.parametrize("detail", ["请重试", {"message": "上传位置不匹配", "offset": 123}])
async def test_expected_http_errors_retain_detail_and_headers(detail):
    api = FastAPI()
    api.add_middleware(SafeErrorMiddleware)

    @api.get("/expected")
    async def expected():
        raise HTTPException(status_code=409, detail=detail, headers={"Upload-Offset": "123"})

    app = FastAPI()
    app.mount("/api", api)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/expected")
    assert response.status_code == 409
    assert response.json() == {"detail": detail}
    assert response.headers["Upload-Offset"] == "123"


async def test_unexpected_errors_never_reach_transport_with_credentials(caplog):
    secret = "synthetic-password-token-never-log"
    api = FastAPI()
    api.add_middleware(SafeErrorMiddleware)

    @api.get("/unexpected")
    async def unexpected():
        raise RuntimeError(secret)

    app = FastAPI()
    app.mount("/api", api)
    with caplog.at_level(logging.DEBUG):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/unexpected", headers={"Authorization": secret, "Cookie": secret})
    assert response.status_code == 500
    assert response.json() == {"detail": "服务器内部错误，请稍后重试"}
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_database_parameters_stay_private_even_with_sql_logger_enabled(caplog, capsys):
    secret = "synthetic-provider-key-database"
    assert get_engine().echo is False
    assert get_engine().sync_engine.hide_parameters is True
    with caplog.at_level(logging.INFO, logger="sqlalchemy.engine"):
        async with get_engine().connect() as connection:
            assert await connection.scalar(text("SELECT :credential"), {"credential": secret}) == secret
            with pytest.raises(DBAPIError) as error:
                await connection.execute(text("SELECT nonexistent_function(:credential)"), {"credential": secret})
    output = capsys.readouterr()
    assert secret not in caplog.text + output.out + output.err + str(error.value)
