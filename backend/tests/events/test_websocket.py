from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.events import ChatEvent, EventPlayer
from app.events.bus import DEFAULT_QUEUE_SIZE
from app.main import app
from app.players.models import Player
from app.servers.models import Server, ServerStatus
from tests.support.auth import create_account, login

PLAYER_UUID = "069a79f444e94726a5befca90e38aaf5"


@pytest.fixture
async def client(db_session_factory, runtime_config):
    await create_account(db_session_factory)
    async with db_session_factory() as session:
        session.add_all([
            Server(id=1, server_id="vanilla", status=ServerStatus.ACTIVE),
            Player(player_db_id=7, uuid=PLAYER_UUID, current_name="Notch"),
        ])
        await session.commit()
    client = TestClient(app)
    try:
        login(client)
        yield client
    finally:
        client.close()


@pytest.fixture
async def history(client, isolated_runtime):
    service = isolated_runtime.player_service
    await service.record_chat_message("vanilla", "Notch", "already seen")
    await service.record_chat_message("vanilla", "Notch", "replayed")


def test_websocket_replays_committed_chat_since_cursor(client, history, isolated_runtime):
    with client.websocket_connect("/api/events?since=1") as websocket:
        frame = websocket.receive_json()
        assert frame["type"] == "chat"
        assert frame["cursor"] == "2"
        assert frame["message"] == "replayed"
        assert frame["server_id"] == "vanilla"
        assert frame["player"] == {"name": "Notch", "uuid": PLAYER_UUID, "player_db_id": 7}
    assert isolated_runtime.event_bus.subscriber_count == 0


def test_websocket_forwards_committed_live_events_and_replays_after_reconnect(client, isolated_runtime):
    with client.websocket_connect("/api/events") as websocket:
        websocket.portal.call(isolated_runtime.player_service.record_chat_message, "vanilla", "Notch", "live")
        frame = websocket.receive_json()
        assert frame["type"] == "chat" and frame["message"] == "live"
        assert frame["cursor"] == "1"
    assert isolated_runtime.event_bus.subscriber_count == 0
    with client.websocket_connect("/api/events?since=0") as websocket:
        replayed = websocket.receive_json()
        assert replayed == frame
    assert isolated_runtime.event_bus.subscriber_count == 0


def test_websocket_dedupes_persisted_cursor_before_forwarding_fresh_chat(client, history, isolated_runtime):
    with client.websocket_connect("/api/events?since=1") as websocket:
        replayed = websocket.receive_json()
        duplicate = ChatEvent.model_validate(replayed)
        websocket.portal.call(isolated_runtime.event_bus.publish, duplicate)
        websocket.portal.call(isolated_runtime.player_service.record_chat_message, "vanilla", "Notch", "fresh")
        fresh = websocket.receive_json()
        assert replayed["cursor"] == "2" and replayed["message"] == "replayed"
        assert fresh["cursor"] == "3" and fresh["message"] == "fresh"
    assert isolated_runtime.event_bus.subscriber_count == 0


@pytest.mark.parametrize("cursor", ["not-an-int", "-1"])
def test_websocket_invalid_cursor_sends_stream_reset_and_goes_live(client, isolated_runtime, cursor):
    with client.websocket_connect(f"/api/events?since={cursor}") as websocket:
        assert websocket.receive_json() == {"type": "stream_reset", "reason": "invalid_cursor"}
        websocket.portal.call(isolated_runtime.player_service.record_chat_message, "vanilla", "Notch", "after reset")
        frame = websocket.receive_json()
        assert frame["type"] == "chat" and frame["message"] == "after reset"
    assert isolated_runtime.event_bus.subscriber_count == 0


def test_websocket_lag_reset_frame_is_sent_then_closed(client, isolated_runtime, monkeypatch):
    monkeypatch.setattr("app.routers.events.HEARTBEAT_INTERVAL", 0.01)
    with client.websocket_connect("/api/events") as websocket:
        assert websocket.receive_json()["type"] == "heartbeat"

        def overwhelm_consumer():
            for index in range(DEFAULT_QUEUE_SIZE + 1):
                isolated_runtime.event_bus.publish(ChatEvent(
                    cursor=str(index + 1), server_id="vanilla", timestamp=datetime.now(UTC),
                    player=EventPlayer(name="Notch", uuid=PLAYER_UUID, player_db_id=7), message="backlog",
                ))

        websocket.portal.call(overwhelm_consumer)
        frame = websocket.receive_json()
        while frame["type"] == "heartbeat":
            frame = websocket.receive_json()
        assert frame == {"type": "stream_reset", "reason": "cursor_too_old"}
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 1013
    assert isolated_runtime.event_bus.subscriber_count == 0


def test_websocket_sends_heartbeat_after_silence(client, isolated_runtime, monkeypatch):
    monkeypatch.setattr("app.routers.events.HEARTBEAT_INTERVAL", 0.01)
    with client.websocket_connect("/api/events") as websocket:
        frame = websocket.receive_json()
        assert frame["type"] == "heartbeat"
        assert datetime.fromisoformat(frame["timestamp"]).tzinfo is not None
    assert isolated_runtime.event_bus.subscriber_count == 0


def test_websocket_rejects_missing_identity_without_subscribing(client, isolated_runtime):
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/events"):
        pytest.fail("Anonymous subscriber was accepted")
    assert isolated_runtime.event_bus.subscriber_count == 0
