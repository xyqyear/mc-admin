"""Bind HTTP, WebSocket and stream execution to the owning application."""

import asyncio

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .operations.context import bind_execution
from .runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


class RuntimeMiddleware:
    def __init__(self, app: ASGIApp, runtime: Runtime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        scoped_app = scope.get("app")
        runtime = getattr(getattr(scoped_app, "state", None), "runtime", self.runtime)
        if runtime.closing:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1013})
            else:
                await JSONResponse(status_code=503, content={"detail": "应用正在关闭，请稍后重试"})(scope, receive, send)
            return
        task = asyncio.current_task()
        nested = task in runtime.requests
        if task is not None:
            runtime.requests.add(task)
        with runtime.bind(), bind_execution(None):
            try:
                await self.app(scope, receive, send)
            finally:
                if task is not None and not nested:
                    runtime.requests.discard(task)
