import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get("WSL_DISTRO_NAME"), "requires WSL with Windows PowerShell 7 and Node")
class WindowsBrowserOwnershipTests(unittest.TestCase):
    def test_owner_disconnect_stops_the_complete_windows_process_tree(self):
        self.check_process_tree(disconnect=True)

    def test_successful_command_reclaims_its_remaining_descendants(self):
        self.check_process_tree(disconnect=False)

    def check_process_tree(self, *, disconnect: bool):
        powershell = shutil.which("pwsh.exe")
        self.assertIsNotNone(powershell)
        assert powershell is not None
        repository = Path(__file__).resolve().parents[2]

        def windows_path(value: Path) -> str:
            return subprocess.check_output(["wslpath", "-w", str(value)], text=True).strip()

        with tempfile.TemporaryDirectory(prefix="mc-admin-browser-job-") as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copyfile(repository / "frontend-react/scripts/wsl-browser.mjs", root / "scripts/wsl-browser.mjs")
            executable = root / "node_modules/@playwright/test/cli.js"
            executable.parent.mkdir(parents=True)
            executable.write_text(
                "const {spawn}=require('node:child_process');\n"
                "const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore',windowsHide:true});\n"
                "require('node:fs').writeFileSync('writers.json',JSON.stringify([process.pid,child.pid]));\n"
                + ("setInterval(()=>{},1000);\n" if disconnect else "setTimeout(()=>process.exit(0),500);\n")
            )
            request = {"directory": windows_path(root), "fixture": "", "metadata": "", "output": "", "distribution": os.environ["WSL_DISTRO_NAME"], "arguments": []}
            payload = base64.b64encode(json.dumps(request).encode()).decode()
            with subprocess.Popen(
                [powershell, "-NoProfile", "-File", windows_path(repository / "scripts/dev/browser_windows.ps1"), "-Payload", payload],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ) as owner:
                try:
                    deadline = time.monotonic() + 20
                    while not (root / "writers.json").exists() and owner.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.1)
                    if not (root / "writers.json").exists():
                        assert owner.stdin is not None
                        owner.stdin.close()
                        owner.stdin = None
                        output, error = owner.communicate(timeout=5)
                        self.fail(f"Browser writers did not start: {output} {error}")
                    writers = json.loads((root / "writers.json").read_text())
                    if not disconnect:
                        owner.wait(timeout=5)
                    assert owner.stdin is not None
                    owner.stdin.close()
                    owner.stdin = None
                    output, error = owner.communicate(timeout=5)
                    self.assertEqual(owner.returncode, 130 if disconnect else 0, output + error)
                    check = subprocess.run(
                        [powershell, "-NoProfile", "-Command", f"if (Get-Process -Id {','.join(map(str, writers))} -ErrorAction SilentlyContinue) {{ exit 1 }}"],
                        check=False, capture_output=True, text=True,
                    )
                    self.assertEqual(check.returncode, 0, "A Windows browser writer survived owner disconnect")
                finally:
                    if owner.poll() is None:
                        assert owner.stdin is not None
                        owner.stdin.close()
                        owner.stdin = None
                        owner.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
