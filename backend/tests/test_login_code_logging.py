from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from app.auth.login_code import LoginCodeManager


async def test_code_rotation_and_expiry_do_not_log_values(monkeypatch, caplog):
    manager = LoginCodeManager()
    codes = ["12345678", "87654321"]
    generated = iter(codes)
    monkeypatch.setattr(manager, "generate_code", lambda: next(generated))
    websocket = MagicMock(spec=WebSocket)
    websocket.send_json = AsyncMock(side_effect=[None, WebSocketDisconnect()])

    with patch("app.auth.login_code.asyncio.sleep", new=AsyncMock()):
        await manager.rotate_code_loop(websocket)

    assert [call.args[0] for call in websocket.send_json.await_args_list] == [
        {"type": "code", "code": code, "timeout": 60} for code in codes
    ]
    assert websocket not in manager.websocket_code_map
    for code in codes:
        assert code not in caplog.text


@pytest.mark.parametrize("error_type", [WebSocketDisconnect, RuntimeError, OSError])
async def test_code_delivery_transport_errors_do_not_log_secret_details(
    error_type, monkeypatch, caplog
):
    manager = LoginCodeManager()
    code = "12345678"
    secret_detail = "transport payload contains " + code
    error = (
        WebSocketDisconnect(reason=secret_detail)
        if error_type is WebSocketDisconnect
        else error_type(secret_detail)
    )
    monkeypatch.setattr(manager, "generate_code", lambda: code)
    websocket = MagicMock(spec=WebSocket)
    websocket.send_json = AsyncMock(side_effect=error)

    await manager.rotate_code_loop(websocket)

    assert websocket not in manager.websocket_code_map
    websocket.send_json.assert_awaited_once_with(
        {"type": "code", "code": code, "timeout": 60}
    )
    assert code not in caplog.text
    assert secret_detail not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_unexpected_code_delivery_error_cleans_mapping_and_propagates(
    monkeypatch, caplog
):
    manager = LoginCodeManager()
    code = "87654321"
    error = LookupError("unexpected payload " + code)
    monkeypatch.setattr(manager, "generate_code", lambda: code)
    websocket = MagicMock(spec=WebSocket)
    websocket.send_json = AsyncMock(side_effect=error)

    with pytest.raises(LookupError) as caught:
        await manager.rotate_code_loop(websocket)

    assert caught.value is error
    assert websocket not in manager.websocket_code_map
    assert code not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
