"""Async subprocess helpers."""

import asyncio
from collections.abc import AsyncGenerator

from ..operations.finalization import finalize
from ..operations.processes import spawn_process, stop_process

_TERMINATE_GRACE_SECONDS = 2.0


async def _kill_process(process: asyncio.subprocess.Process) -> None:
    """SIGTERM, wait up to _TERMINATE_GRACE_SECONDS, then SIGKILL."""
    await stop_process(process, grace=_TERMINATE_GRACE_SECONDS)


async def exec_command(
    command: str,
    *args: str,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
) -> str:
    """Run ``command`` and return stdout. Raises ``RuntimeError`` on non-zero exit
    or ``TimeoutError`` when ``timeout`` expires; the subprocess is killed
    (SIGTERM then SIGKILL after a grace) before either is raised.
    """
    process = await spawn_process(
        command,
        *args,
        env={} if env is None else env,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        if timeout is None:
            stdout, stderr = await process.communicate()
        else:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
    except TimeoutError:
        await finalize(_kill_process(process))
        raise TimeoutError(
            f"Command timed out after {timeout}s: {command} {' '.join(args)}"
        )
    except BaseException:
        # Cancellation must not orphan the child process.
        await finalize(_kill_process(process))
        raise

    await finalize(_kill_process(process))

    if stdout is None:  # type: ignore
        stdout = b""
    if stderr is None:  # type: ignore
        stderr = b""

    if process.returncode != 0:
        raise RuntimeError(
            f"Failed to exec command: {command}\n{stderr.decode()}\n{stdout.decode()}"
        )
    return stdout.decode()


async def exec_command_stream(
    command: str,
    *args: str,
    cwd: str | None = None,
    delimiters: set[int] | None = None,
) -> AsyncGenerator[str]:
    """Stream stdout segments from ``command``.

    ``delimiters=None`` yields whole lines. Pass a set of byte values (e.g.
    ``{ord('\\r'), ord('\\n'), ord('\\x08')}`` for 7z progress) to split on
    arbitrary control bytes. Raises ``RuntimeError`` on non-zero exit.
    """
    process = await spawn_process(
        command,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_chunks: list[bytes] = []

    async def drain_stderr() -> None:
        if process.stderr is not None:
            while chunk := await process.stderr.read(4096):
                stderr_chunks.append(chunk)
                if len(stderr_chunks) > 64:
                    del stderr_chunks[0]

    stderr_task = asyncio.create_task(drain_stderr())
    try:
        if process.stdout is None:
            raise RuntimeError("Failed to capture stdout")

        if delimiters is None:
            async for line in process.stdout:
                yield line.decode()
        else:
            buffer = b""
            while True:
                byte = await process.stdout.read(1)
                if not byte:
                    break

                if byte[0] in delimiters:
                    if buffer:
                        yield buffer.decode(errors="replace")
                        buffer = b""
                else:
                    buffer += byte

            if buffer:
                yield buffer.decode(errors="replace")

        await process.wait()
        await stderr_task
        if process.returncode != 0:
            stderr_content = b"".join(stderr_chunks)
            raise RuntimeError(f"Command failed: {stderr_content.decode()}")
    finally:
        async def cleanup() -> None:
            if not stderr_task.done():
                stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
            await _kill_process(process)

        await finalize(cleanup())
