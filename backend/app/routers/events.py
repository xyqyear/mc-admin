import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from ..db.database import get_async_session
from ..dependencies import get_websocket_user
from ..events import (
    ChatEvent,
    EventPlayer,
    HeartbeatFrame,
    PublicEventFrame,
    StreamResetFrame,
    event_bus,
)
from ..models import UserPublic
from ..players.crud.query.chat_query import ChatEventInfo, get_chat_messages_after

HEARTBEAT_INTERVAL = 25.0
REPLAY_BATCH_SIZE = 500

router = APIRouter(tags=["events"])


def _chat_event_from_info(info: ChatEventInfo) -> ChatEvent:
    return ChatEvent(
        cursor=str(info.message_id),
        server_id=info.server_id,
        timestamp=info.sent_at,
        player=EventPlayer(
            name=info.player_name,
            uuid=info.player_uuid,
            player_db_id=info.player_db_id,
        ),
        message=info.message_text,
    )


async def _send_frame(websocket: WebSocket, frame: PublicEventFrame) -> None:
    await websocket.send_json(frame.model_dump(mode="json"))


async def _replay_chat(websocket: WebSocket, since_id: int) -> int:
    after_id = since_id
    max_replayed_id = since_id

    async with get_async_session() as session:
        while True:
            messages = await get_chat_messages_after(
                session,
                after_id=after_id,
                limit=REPLAY_BATCH_SIZE,
            )
            if not messages:
                break

            for message in messages:
                await _send_frame(websocket, _chat_event_from_info(message))
                after_id = message.message_id
                max_replayed_id = message.message_id

            if len(messages) < REPLAY_BATCH_SIZE:
                break

    return max_replayed_id


@router.websocket("/events")
async def events_websocket(
    websocket: WebSocket,
    since: str | None = Query(default=None),
    _: UserPublic = Depends(get_websocket_user),
):
    await websocket.accept()
    subscription = event_bus.subscribe()
    max_replayed_id = 0

    try:
        if since is not None:
            try:
                since_id = int(since)
                if since_id < 0:
                    raise ValueError
            except ValueError:
                await _send_frame(websocket, StreamResetFrame(reason="invalid_cursor"))
            else:
                max_replayed_id = await _replay_chat(websocket, since_id)

        while True:
            try:
                frame = await asyncio.wait_for(
                    subscription.queue.get(),
                    timeout=HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                await _send_frame(
                    websocket,
                    HeartbeatFrame(timestamp=datetime.now(timezone.utc)),
                )
                continue

            if isinstance(frame, ChatEvent) and int(frame.cursor) <= max_replayed_id:
                continue

            await _send_frame(websocket, frame)

            if isinstance(frame, StreamResetFrame):
                await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
                break
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(subscription)
