"""Bounded container commands, independent of monitoring and Compose lifecycle."""

import asyncio
import contextvars
import math
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import docker
import requests
from docker.errors import DockerException, NotFound

from ...logger import get_logger
from ...operations.finalization import finalize
from .reader import ContainerState

RCON_TIMEOUT = 10.0
RCON_EXECUTION_TIMEOUT = 8.0

_TIMEOUT_COMMAND = 'tool=$(command -v gnutimeout) || tool=timeout; exec "$tool" --kill-after=1s "$@"'


class ServerMissing(RuntimeError):
    pass


class ServerUnavailable(RuntimeError):
    pass


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("容器命令执行超时")
    return remaining


def _read_output(connection: socket.socket, deadline: float) -> bytes:
    def read_exactly(size: int, *, eof: bool = False) -> bytes:
        data = bytearray()
        while len(data) < size:
            connection.settimeout(_remaining(deadline))
            chunk = connection.recv(min(size - len(data), 65536))
            if not chunk:
                if eof and not data:
                    return b""
                raise RuntimeError("Docker 命令输出连接意外关闭")
            data.extend(chunk)
        return bytes(data)

    output = bytearray()
    while header := read_exactly(8, eof=True):
        stream, length = struct.unpack(">BxxxI", header)
        if stream not in (1, 2):
            raise RuntimeError("Docker 命令输出格式无效")
        while length:
            chunk = read_exactly(min(length, 65536))
            if stream == 1:
                output.extend(chunk)
            length -= len(chunk)
    return bytes(output)


class DockerCommands:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker-command")
        self._slots = asyncio.Semaphore(4)
        self._pending: set[asyncio.Future[str]] = set()
        self._closing = False

    async def execute(
        self, container: ContainerState, argv: list[str], *,
        execution_timeout: float, timeout: float, kind: str,
    ) -> str:
        if not all(math.isfinite(value) and value > 0 for value in (execution_timeout, timeout)):
            raise RuntimeError("命令超时必须是正有限秒数")
        deadline = time.monotonic() + timeout
        async with asyncio.timeout(timeout):
            await self._slots.acquire()
            if self._closing:
                self._slots.release()
                raise RuntimeError("Docker 命令服务已关闭")
            try:
                context = contextvars.copy_context()
                future = asyncio.get_running_loop().run_in_executor(
                    self._executor,
                    lambda: context.run(self._execute, container, argv, execution_timeout, deadline, kind),
                )
            except BaseException:
                self._slots.release()
                raise
            self._pending.add(future)
            future.add_done_callback(self._finished)
            return await asyncio.shield(future)

    def _finished(self, future: asyncio.Future[str]) -> None:
        self._pending.discard(future)
        self._slots.release()
        if not future.cancelled():
            future.exception()

    def _execute(
        self, container: ContainerState, argv: list[str], execution_timeout: float,
        deadline: float, kind: str,
    ) -> str:
        started = time.monotonic()
        stage = "connect"
        exit_code = None
        client = None
        try:
            client = docker.from_env(timeout=math.ceil(min(2.0, _remaining(deadline))))
            api = client.api
            stage = "identity"
            api.timeout = math.ceil(min(2.0, _remaining(deadline)))
            state = api.inspect_container(container.container_id)["State"]
            if (state.get("StartedAt") != container.started_at or not state.get("Running")
                    or (state.get("Health") or {}).get("Status") != "healthy"):
                raise ServerUnavailable("服务器运行实例已改变或未在健康状态")
            duration = min(execution_timeout, _remaining(deadline) - 2.0)
            if duration <= 0:
                raise TimeoutError("容器命令准备超时")
            stage = "create"
            api.timeout = math.ceil(min(2.0, _remaining(deadline)))
            identifier = api.exec_create(
                container.container_id,
                ["sh", "-c", _TIMEOUT_COMMAND, "mc-admin-command", str(duration), *argv],
                stdin=False, tty=False,
            )["Id"]
            stage = "start"
            api.timeout = math.ceil(min(2.0, _remaining(deadline)))
            attached = api.exec_start(identifier, socket=True, tty=False)
            try:
                stage = "output"
                connection = cast(socket.socket, getattr(attached, "_sock", attached))
                output = _read_output(connection, deadline)
            finally:
                response = getattr(attached, "_response", None)
                try:
                    if response is not None:
                        response.close()
                finally:
                    attached.close()
            stage = "exit"
            while True:
                api.timeout = math.ceil(min(2.0, _remaining(deadline)))
                result = api.exec_inspect(identifier)
                if not result["Running"]:
                    break
                time.sleep(min(0.01, _remaining(deadline)))
            exit_code = result["ExitCode"]
            if exit_code in (124, 137):
                raise TimeoutError(f"容器命令超时或被终止（退出码 {exit_code}）")
            if exit_code != 0:
                raise RuntimeError(f"容器命令执行失败（退出码 {exit_code}）")
            return output.decode(errors="replace")
        except NotFound:
            raise ServerUnavailable("服务器运行实例已不存在") from None
        except (TimeoutError, requests.exceptions.Timeout):
            raise TimeoutError("容器命令执行或通信超时") from None
        except (DockerException, requests.exceptions.RequestException, OSError):
            raise RuntimeError("Docker 命令通信失败，执行结果未知") from None
        finally:
            if client is not None:
                client.close()
            get_logger().debug(
                "Container command kind=%s stage=%s exit=%s elapsed_ms=%.1f",
                kind, stage, exit_code, (time.monotonic() - started) * 1000,
            )

    async def close(self) -> None:
        self._closing = True
        await finalize(asyncio.gather(*self._pending, return_exceptions=True))
        self._executor.shutdown(wait=True)
