import asyncio
import random

from asyncer import syncify
from auth.jwt_utils import create_access_token
from db.crud.user import get_user_by_username
from db.database import get_session
from fastapi import WebSocket, WebSocketDisconnect
from logger import logger


class LoginCodeManager:
    def __init__(self):
        self.websocket_code_map: dict[WebSocket, str] = {}

    def generate_code(self):
        return "".join(random.choices("0123456789", k=8))

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

    def verify_user_with_code(self, username: str, code: str):
        with get_session() as session:
            user = get_user_by_username(session, username=username)
            if user is None:
                return False
        websocket = self.find_websocket_by_code(code)
        if websocket is None:
            return False

        access_token = create_access_token(data={"sub": user.username})
        try:
            syncify(websocket.send_json)(
                {"type": "verified", "access_token": access_token}
            )
        except WebSocketDisconnect:
            self.websocket_code_map.pop(websocket, None)
            return False

        return True


loginCodeManager = LoginCodeManager()
