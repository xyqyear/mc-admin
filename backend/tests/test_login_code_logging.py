from unittest.mock import AsyncMock, MagicMock, patch

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
