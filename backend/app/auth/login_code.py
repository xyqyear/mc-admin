import asyncio
import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket, WebSocketDisconnect

from ..db.crud.user import get_user_by_username
from ..logger import logger
from ..models import UserPublic
from .session import user_to_public


@dataclass(frozen=True)
class LoginCompletion:
    user: UserPublic
    expires_at: datetime


class LoginCodeManager:
    def __init__(self):
        self.websocket_code_map: dict[WebSocket, str] = {}
        self.completion_tickets: dict[str, LoginCompletion] = {}

    def generate_code(self):
        return "".join(random.choices("0123456789", k=8))

    def generate_ticket(self):
        return secrets.token_urlsafe(32)

    async def manage_websocket(self, websocket: WebSocket):
        await websocket.accept()
        assert websocket.client is not None
        logger.info(
            f"Websocket from {websocket.client.host}:{websocket.client.port} connected"
        )
        rotate_code_task = asyncio.create_task(self.rotate_code_loop(websocket))
        try:
            while True:
                received = await websocket.receive_text()
                if received == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            logger.info(
                f"Websocket from {websocket.client.host}:{websocket.client.port} disconnected"
            )
            self.websocket_code_map.pop(websocket, None)
            rotate_code_task.cancel()

    async def rotate_code_loop(self, websocket: WebSocket):
        while True:
            code = self.generate_code()
            self.websocket_code_map[websocket] = code
            try:
                logger.info(f"Sending code {code} to client")
                await websocket.send_json({"type": "code", "code": code, "timeout": 60})
            except Exception:
                logger.info("Client already disconnected")
                self.websocket_code_map.pop(websocket, None)
                break
            await asyncio.sleep(60)
            logger.info(f"Code {code} expired")

    def find_websocket_by_code(self, code: str):
        for websocket, ws_code in self.websocket_code_map.items():
            if ws_code == code:
                return websocket
        return None

    def _remove_expired_tickets(self) -> None:
        now = datetime.now(timezone.utc)
        for ticket, completion in list(self.completion_tickets.items()):
            if completion.expires_at <= now:
                self.completion_tickets.pop(ticket, None)

    async def verify_user_with_code(self, session, username: str, code: str):
        self._remove_expired_tickets()
        user = await get_user_by_username(session, username=username)
        if user is None:
            return False
        websocket = self.find_websocket_by_code(code)
        if websocket is None:
            return False

        try:
            public_user = user_to_public(user)
        except ValueError:
            return False

        ticket = self.generate_ticket()
        self.completion_tickets[ticket] = LoginCompletion(
            user=public_user,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        try:
            await websocket.send_json({"type": "verified", "ticket": ticket})
        except WebSocketDisconnect:
            self.websocket_code_map.pop(websocket, None)
            self.completion_tickets.pop(ticket, None)
            return False

        self.websocket_code_map.pop(websocket, None)
        return True

    def complete_login(self, ticket: str) -> UserPublic | None:
        self._remove_expired_tickets()
        completion = self.completion_tickets.pop(ticket, None)
        if completion is None:
            return None
        return completion.user


loginCodeManager = LoginCodeManager()
