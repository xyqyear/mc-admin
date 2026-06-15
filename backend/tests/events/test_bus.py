from datetime import datetime, timezone

from app.events import ChatEvent, EventBus, EventPlayer, StreamResetFrame


def chat_event(cursor: str = "1") -> ChatEvent:
    return ChatEvent(
        cursor=cursor,
        server_id="vanilla",
        timestamp=datetime.now(timezone.utc),
        player=EventPlayer(name="Notch", uuid="069a79f4", player_db_id=7),
        message="hello",
    )


def test_event_bus_fans_out_to_all_subscribers():
    bus = EventBus()
    first = bus.subscribe()
    second = bus.subscribe()
    event = chat_event()

    bus.publish(event)

    assert first.queue.get_nowait() == event
    assert second.queue.get_nowait() == event


def test_event_bus_marks_slow_subscriber_lagged_and_drops_it():
    bus = EventBus()
    subscription = bus.subscribe(maxsize=1)

    bus.publish(chat_event("1"))
    bus.publish(chat_event("2"))

    assert subscription.lagged is True
    assert bus.subscriber_count == 0
    frame = subscription.queue.get_nowait()
    assert isinstance(frame, StreamResetFrame)
    assert frame.reason == "cursor_too_old"
