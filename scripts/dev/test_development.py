import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("development_server", Path(__file__).with_name("server.py"))
assert spec is not None and spec.loader is not None
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DevelopmentEnvironmentTests(unittest.TestCase):
    def test_initialization_keeps_credentials_and_data_private_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, data = root / "config", root / "data"
            server.initialize(config, data)
            original = (config / "config.toml").read_text()
            self.assertIn(str(data / "db.sqlite3"), original)
            self.assertEqual((config / "config.toml").stat().st_mode & 0o077, 0)
            self.assertTrue((data / "static/static").is_dir())
            (config / "config.toml").write_text(original + "\n# personal configuration\n")
            (data / "sentinel").write_bytes(b"existing data")
            server.initialize(config, data)
            self.assertTrue((config / "config.toml").read_text().endswith("# personal configuration\n"))
            self.assertEqual((data / "sentinel").read_bytes(), b"existing data")

    def test_windows_runtime_directory_is_rejected(self):
        with (
            patch.dict(os.environ, {"MC_ADMIN_DEV_DATA": "/mnt/d/development"}),
            self.assertRaisesRegex(ValueError, "Linux filesystem"),
        ):
            server.locations()

    def test_stop_checks_process_identity_and_waits_for_exit(self):
        with tempfile.TemporaryDirectory() as directory, subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"]
        ) as child:
            data = Path(directory)
            try:
                state = {"pid": child.pid, "start": "wrong-start-time"}
                (data / "devserver.json").write_text(json.dumps(state))
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    server.stop(data)
                self.assertIsNone(child.poll())
                state["start"] = server.process_start(child.pid)
                (data / "devserver.json").write_text(json.dumps(state))
                server.stop(data)
                self.assertEqual(child.wait(timeout=2), -15)
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=2)

    def test_launcher_preserves_arguments_exit_code_and_external_environment(self):
        with tempfile.TemporaryDirectory(prefix="mc admin ") as directory:
            root = Path(directory)
            binary = root / ".local/bin/uv"
            binary.parent.mkdir(parents=True)
            binary.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "print(json.dumps([sys.argv[1:], os.getcwd(), os.environ['UV_PROJECT_ENVIRONMENT']]))\n"
                "sys.exit(17)\n"
            )
            binary.chmod(0o700)
            script = Path(__file__).with_name("backend.sh")
            env = {**os.environ, "HOME": directory}
            env.pop("MC_ADMIN_LINUX_VENV", None)
            result = subprocess.run(
                ["bash", str(script), "run", "python", "-c", "space ' quote \" $ literal"],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 17, result.stderr)
            arguments, cwd, virtualenv = json.loads(result.stdout)
            self.assertEqual(arguments[-1], "space ' quote \" $ literal")
            self.assertEqual(Path(cwd).name, "backend")
            self.assertEqual(virtualenv, str(root / ".venvs/mc-admin-backend"))

    def test_launcher_rejects_unfiltered_tests_before_running_uv(self):
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("backend.sh")), "test"], text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit", result.stderr)

    def test_e2e_launcher_requires_case_and_browser_filters(self):
        for arguments in (["run"], ["browser", "--", "browser/navigation.spec.ts"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    ["bash", str(Path(__file__).with_name("e2e.sh")), *arguments],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("require", result.stderr)


if __name__ == "__main__":
    unittest.main()
