from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.events import ChatEvent, EventPlayer, StreamResetFrame
from app.events.bus import Subscription
from app.main import api_app
from app.players.crud.query.chat_query import ChatEventInfo


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-master-token"}


def timestamp() -> datetime:
    return datetime(2026, 6, 15, tzinfo=timezone.utc)


def chat_info(message_id: int, message: str) -> ChatEventInfo:
    return ChatEventInfo(
        message_id=message_id,
        server_id="vanilla",
        player_db_id=7,
        player_name="Notch",
        player_uuid="069a79f4",
        message_text=message,
        sent_at=timestamp(),
    )


def chat_event(cursor: str, message: str) -> ChatEvent:
    return ChatEvent(
        cursor=cursor,
        server_id="vanilla",
        timestamp=timestamp(),
        player=EventPlayer(name="Notch", uuid="069a79f4", player_db_id=7),
        message=message,
    )


def subscription_with(*frames) -> Subscription:
    subscription = Subscription()
    for frame in frames:
        subscription.queue.put_nowait(frame)
    return subscription


@asynccontextmanager
async def dummy_session():
    yield object()


@pytest.fixture
def client():
    with patch("app.auth.session.settings.master_token", "test-master-token"):
        yield TestClient(api_app)


def test_websocket_replays_chat_since_cursor(client):
    with (
        patch("app.routers.events.get_async_session", dummy_session),
        patch(
            "app.routers.events.get_chat_messages_after",
            AsyncMock(return_value=[chat_info(2, "replayed")]),
        ),
        patch(
            "app.routers.events.event_bus.subscribe",
            return_value=subscription_with(),
        ),
    ):
        with client.websocket_connect(
            "/events?since=1",
            headers=auth_headers(),
        ) as websocket:
            frame = websocket.receive_json()

    assert frame["type"] == "chat"
    assert frame["cursor"] == "2"
    assert frame["message"] == "replayed"
    assert frame["player"]["name"] == "Notch"


def test_websocket_forwards_live_events(client):
    live = chat_event("4", "live")

    with patch(
        "app.routers.events.event_bus.subscribe",
        return_value=subscription_with(live),
    ):
        with client.websocket_connect("/events", headers=auth_headers()) as websocket:
            frame = websocket.receive_json()

    assert frame["type"] == "chat"
    assert frame["cursor"] == "4"
    assert frame["message"] == "live"


def test_websocket_dedupes_live_event_already_seen_in_replay(client):
    duplicate = chat_event("2", "duplicate")
    live = chat_event("3", "fresh")

    with (
        patch("app.routers.events.get_async_session", dummy_session),
        patch(
            "app.routers.events.get_chat_messages_after",
            AsyncMock(return_value=[chat_info(2, "replayed")]),
        ),
        patch(
            "app.routers.events.event_bus.subscribe",
            return_value=subscription_with(duplicate, live),
        ),
    ):
        with client.websocket_connect(
            "/events?since=1",
            headers=auth_headers(),
        ) as websocket:
            replayed = websocket.receive_json()
            fresh = websocket.receive_json()

    assert replayed["cursor"] == "2"
    assert replayed["message"] == "replayed"
    assert fresh["cursor"] == "3"
    assert fresh["message"] == "fresh"


def test_websocket_invalid_cursor_sends_stream_reset_and_goes_live(client):
    live = chat_event("5", "after reset")

    with patch(
        "app.routers.events.event_bus.subscribe",
        return_value=subscription_with(live),
    ):
        with client.websocket_connect(
            "/events?since=not-an-int",
            headers=auth_headers(),
        ) as websocket:
            reset = websocket.receive_json()
            frame = websocket.receive_json()

    assert reset == {"type": "stream_reset", "reason": "invalid_cursor"}
    assert frame["type"] == "chat"
    assert frame["cursor"] == "5"


def test_websocket_lag_reset_frame_is_sent_then_closed(client):
    with patch(
        "app.routers.events.event_bus.subscribe",
        return_value=subscription_with(StreamResetFrame(reason="cursor_too_old")),
    ):
        with client.websocket_connect("/events", headers=auth_headers()) as websocket:
            frame = websocket.receive_json()

    assert frame == {"type": "stream_reset", "reason": "cursor_too_old"}


def test_websocket_sends_heartbeat_after_silence(client):
    with (
        patch("app.routers.events.HEARTBEAT_INTERVAL", 0.01),
        patch(
            "app.routers.events.event_bus.subscribe",
            return_value=subscription_with(),
        ),
    ):
        with client.websocket_connect("/events", headers=auth_headers()) as websocket:
            frame = websocket.receive_json()

    assert frame["type"] == "heartbeat"
    assert "timestamp" in frame
