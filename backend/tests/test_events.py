"""Tests for event system (dispatcher and event types)."""

import asyncio
from datetime import datetime, timezone
from typing import List

import pytest

from app.events.base import PlayerJoinedEvent
from app.events.dispatcher import EventDispatcher


class TestEventDispatcher:
    """Test event dispatcher functionality."""

    @pytest.mark.asyncio
    async def test_dispatch_player_joined_event(self):
        """Test dispatching player joined event to registered handlers."""
        dispatcher = EventDispatcher()

        # Track handler calls
        handler_called = asyncio.Event()
        received_events: List[PlayerJoinedEvent] = []

        # Register async handler
        async def async_handler(event: PlayerJoinedEvent) -> None:
            received_events.append(event)
            handler_called.set()

        dispatcher.on_player_joined(async_handler)

        # Create and dispatch event
        event = PlayerJoinedEvent(
            server_id="test_server",
            player_name="TestPlayer",
            timestamp=datetime.now(timezone.utc),
        )

        await dispatcher.dispatch_player_joined(event)

        # Wait for handler to complete
        await asyncio.wait_for(handler_called.wait(), timeout=1.0)

        # Verify handler was called with correct event
        assert len(received_events) == 1
        assert received_events[0].server_id == "test_server"
        assert received_events[0].player_name == "TestPlayer"

    @pytest.mark.asyncio
    async def test_dispatch_with_multiple_handlers(self):
        """Test dispatching event to multiple handlers."""
        dispatcher = EventDispatcher()

        # Track handler calls
        handler1_calls = []
        handler2_calls = []

        # Register two async and sync handlers
        async def handler1(event: PlayerJoinedEvent) -> None:
            handler1_calls.append(event)

        def handler2(event: PlayerJoinedEvent) -> None:
            handler2_calls.append(event)

        dispatcher.on_player_joined(handler1)
        dispatcher.on_player_joined(handler2)

        # Create and dispatch event
        event = PlayerJoinedEvent(server_id="test_server", player_name="TestPlayer")

        await dispatcher.dispatch_player_joined(event)

        # Give handlers time to complete
        await asyncio.sleep(0.1)

        # Verify both handlers were called
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1
        assert handler1_calls[0].player_name == "TestPlayer"
        assert handler2_calls[0].player_name == "TestPlayer"

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_other_handlers(self):
        """Test that error in one handler doesn't prevent other handlers from running."""
        dispatcher = EventDispatcher()

        # Track handler calls
        handler1_calls = []
        handler2_calls = []

        # Register handlers where first one raises error
        async def failing_handler(event: PlayerJoinedEvent) -> None:
            handler1_calls.append(event)
            raise ValueError("Test error")

        async def successful_handler(event: PlayerJoinedEvent) -> None:
            handler2_calls.append(event)

        dispatcher.on_player_joined(failing_handler)
        dispatcher.on_player_joined(successful_handler)

        # Create and dispatch event
        event = PlayerJoinedEvent(server_id="test_server", player_name="TestPlayer")

        await dispatcher.dispatch_player_joined(event)

        # Give handlers time to complete
        await asyncio.sleep(0.1)

        # Verify both handlers were called despite error
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    @pytest.mark.asyncio
    async def test_no_handlers_registered(self):
        """Test dispatching event when no handlers are registered."""
        dispatcher = EventDispatcher()

        # Create and dispatch event
        event = PlayerJoinedEvent(server_id="test_server", player_name="TestPlayer")

        # Should not raise error
        await dispatcher.dispatch_player_joined(event)
