import asyncio
import random

from fastapi import WebSocket, WebSocketDisconnect

from ..db.crud.user import get_user_by_username
from ..dependencies import JwtClaims
from ..logger import logger
from .jwt_utils import create_access_token, get_token_expiry


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

    async def verify_user_with_code(self, session, username: str, code: str):
        user = await get_user_by_username(session, username=username)
        if user is None:
            return False
        websocket = self.find_websocket_by_code(code)
        if websocket is None:
            return False

        # 用户登录时 id 不应该为 None
        if user.id is None:
            return False

        # 使用 JwtClaims 创建 JWT 数据
        jwt_claims = JwtClaims(
            sub=user.username,
            user_id=user.id,
            username=user.username,
            role=user.role.value,
            created_at=user.created_at.isoformat(),
            exp=get_token_expiry(),
        )
        access_token = create_access_token(jwt_claims)
        try:
            await websocket.send_json(
                {"type": "verified", "access_token": access_token}
            )
        except WebSocketDisconnect:
            self.websocket_code_map.pop(websocket, None)
            return False

        return True


loginCodeManager = LoginCodeManager()
