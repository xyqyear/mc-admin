"""Async subprocess helpers."""

import asyncio
from collections.abc import AsyncGenerator


_TERMINATE_GRACE_SECONDS = 2.0


async def _kill_process(process: asyncio.subprocess.Process) -> None:
    """SIGTERM, wait up to _TERMINATE_GRACE_SECONDS, then SIGKILL."""
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_SECONDS)
        return
    except asyncio.TimeoutError:
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    await process.wait()


async def exec_command(
    command: str,
    *args: str,
    env: dict[str, str] = dict(),
    cwd: str | None = None,
    timeout: float | None = None,
) -> str:
    """Run ``command`` and return stdout. Raises ``RuntimeError`` on non-zero exit
    or ``TimeoutError`` when ``timeout`` expires; the subprocess is killed
    (SIGTERM then SIGKILL after a grace) before either is raised.
    """
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        env=env,
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
    except asyncio.TimeoutError:
        await _kill_process(process)
        raise TimeoutError(
            f"Command timed out after {timeout}s: {command} {' '.join(args)}"
        )
    except BaseException:
        # Cancellation must not orphan the child process.
        await _kill_process(process)
        raise

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
) -> AsyncGenerator[str, None]:
    """Stream stdout segments from ``command``.

    ``delimiters=None`` yields whole lines. Pass a set of byte values (e.g.
    ``{ord('\\r'), ord('\\n'), ord('\\x08')}`` for 7z progress) to split on
    arbitrary control bytes. Raises ``RuntimeError`` on non-zero exit.
    """
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

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
    if process.returncode != 0:
        stderr_content = b""
        if process.stderr:
            stderr_content = await process.stderr.read()
        raise RuntimeError(f"Command failed: {stderr_content.decode()}")
