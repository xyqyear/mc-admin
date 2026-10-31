import base64
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


def windows_path(value: str) -> str:
    return subprocess.check_output(["wslpath", "-w", str(Path(value).resolve())], text=True).strip()


def main() -> int:
    repository = Path(__file__).resolve().parents[2]
    fixture = os.environ["MC_ADMIN_BROWSER_FIXTURE"]
    metadata = os.environ.get("MC_ADMIN_BROWSER_CLIENT_METADATA")
    output = os.environ.get("BROWSER_OUTPUT_DIR")
    request = {
        "fixture": fixture,
        "distribution": os.environ["WSL_DISTRO_NAME"],
        "directory": windows_path(str(repository / "frontend-react")),
        "metadata": windows_path(metadata) if metadata else "",
        "output": windows_path(output) if output else "",
        "arguments": sys.argv[1:],
    }
    payload = base64.b64encode(json.dumps(request).encode()).decode()
    powershell = shutil.which("pwsh.exe")
    if powershell is None:
        raise RuntimeError("PowerShell 7 must be available to WSL as pwsh.exe")
    script = windows_path(str(repository / "scripts/dev/browser_windows.ps1"))
    child = subprocess.Popen([powershell, "-NoProfile", "-File", script, "-Payload", payload], stdin=subprocess.PIPE)

    def interrupted(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        return child.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        assert child.stdin is not None
        child.stdin.close()
        child.wait(timeout=4)


if __name__ == "__main__":
    sys.exit(main())
