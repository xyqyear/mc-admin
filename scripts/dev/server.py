import fcntl
import json
import os
import secrets
import select
import signal
import sys
from pathlib import Path


def locations() -> tuple[Path, Path]:
    config = Path(os.environ.get("MC_ADMIN_DEV_CONFIG", Path.home() / ".config/mc-admin-dev"))
    data = Path(os.environ.get("MC_ADMIN_DEV_DATA", Path.home() / ".local/share/mc-admin-dev"))
    for directory in (config, data):
        if not directory.is_absolute() or str(directory.resolve()).startswith("/mnt/"):
            raise ValueError("Development configuration and data require absolute Linux filesystem paths")
    return config, data


def initialize(config: Path, data: Path) -> None:
    config.mkdir(parents=True, exist_ok=True, mode=0o700)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    static = data / "static"
    (static / "assets").mkdir(parents=True, exist_ok=True)
    public = Path(__file__).resolve().parents[2] / "frontend-react/public"
    for name in ("static", "robots.txt"):
        target = static / name
        if not target.exists():
            target.symlink_to(public / name, target_is_directory=(name == "static"))
    values = {
        "master_token": secrets.token_urlsafe(32),
        "database_url": f"sqlite+aiosqlite:///{data / 'db.sqlite3'}",
        "server_path": str(data / "servers"),
        "logs_dir": str(data / "logs"),
        "archive_path": str(data / "archives"),
        "static_path": str(static),
    }
    content = "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items())
    content += f'\n\n[jwt]\nsecret_key = {json.dumps(secrets.token_urlsafe(48))}\n'
    for name, text in (("config.toml", content), (".env", "")):
        try:
            descriptor = os.open(config / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)


def process_start(pid: int) -> str:
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def stop(data: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from app.operations.pidfd import open_pidfd, send_signal

    state_path = data / "devserver.json"
    if not state_path.exists():
        print("No development backend is running.")
        return
    state = json.loads(state_path.read_text())
    try:
        descriptor = open_pidfd(state["pid"])
    except ProcessLookupError:
        print("The recorded development backend has already stopped.")
        return
    try:
        if process_start(state["pid"]) != state["start"]:
            raise RuntimeError("Development process identity changed; refusing to signal it")
        send_signal(descriptor, signal.SIGTERM)
        if not select.select([descriptor], [], [], 30)[0]:
            raise RuntimeError("Development backend is still draining; it was not forcibly killed")
    finally:
        os.close(descriptor)


def serve(action: str, config: Path, data: Path) -> None:
    import uvicorn

    initialize(config, data)
    os.environ["MC_ADMIN_CONFIG"] = str(config / "config.toml")
    os.environ["MC_ADMIN_ENV"] = str(config / ".env")
    os.environ["WATCHFILES_FORCE_POLLING"] = "true"
    os.environ.setdefault("WATCHFILES_POLL_DELAY_MS", "500")
    state_path = data / "devserver.json"
    with (data / "devserver.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("This development backend is already running; stop it first") from None
        state_path.write_text(json.dumps({"pid": os.getpid(), "start": process_start(os.getpid())}))
        try:
            if action == "debug":
                import debugpy  # noqa: T100

                debugpy.listen(("127.0.0.1", 5679))  # noqa: T100
                print("MC_ADMIN_DEBUG_READY", flush=True)
            uvicorn.run(
                "app.main:app",
                app_dir=str(Path.cwd()),
                host="127.0.0.1",
                port=5678,
                reload=True,
                reload_dirs=["app", "alembic"],
                timeout_graceful_shutdown=2,
                log_level="info",
            )
        finally:
            state_path.unlink(missing_ok=True)


def main() -> None:
    action = sys.argv[1]
    config, data = locations()
    if action == "init":
        initialize(config, data)
        print(f"Development configuration: {config / 'config.toml'}")
        print(f"Development data: {data}")
    elif action == "stop":
        stop(data)
    else:
        serve(action, config, data)


if __name__ == "__main__":
    main()
