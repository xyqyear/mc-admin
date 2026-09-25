import os
import shutil
import tempfile
from pathlib import Path


def isolated_environment(root: Path) -> dict[str, str]:
    for name in ("servers", "archives", "logs", "static/assets", "static/static"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text("")
    (root / ".env").write_text("")
    public = Path(__file__).resolve().parents[3] / "frontend-react" / "public"
    if not public.exists():
        public = Path(__file__).resolve().parents[4] / "frontend-react" / "public"
    if public.exists():
        shutil.copytree(public, root / "static", dirs_exist_ok=True)
    (root / "static/index.html").write_text("<!doctype html><html><body></body></html>\n")
    return {
        "MC_ADMIN_CONFIG": str(root / "config.toml"),
        "MC_ADMIN_ENV": str(root / ".env"),
        "MASTER_TOKEN": "test-master-token",
        "JWT__SECRET_KEY": "isolated-pytest-secret-key-at-least-32-bytes",
        "SERVER_PATH": str(root / "servers"),
        "ARCHIVE_PATH": str(root / "archives"),
        "LOGS_DIR": str(root / "logs"),
        "STATIC_PATH": str(root / "static"),
        "DATABASE_URL": f"sqlite+aiosqlite:///{root / 'application.sqlite3'}",
    }


def configure_test_environment() -> tempfile.TemporaryDirectory[str]:
    directory = tempfile.TemporaryDirectory(prefix="mc-admin-pytest-")
    for name in list(os.environ):
        if name in {"RESTIC", "JWT", "AUDIT"} or name.startswith(
            ("RESTIC__", "JWT__", "AUDIT__")
        ):
            del os.environ[name]
    os.environ.update(isolated_environment(Path(directory.name)))
    return directory
