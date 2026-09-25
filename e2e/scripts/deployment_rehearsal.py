"""Exercise released-code upgrade and bounded rollback in an owned fixture."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class Deployment:
    def __init__(self, fixture):
        self.fixture = fixture
        self.server = fixture["server_id"]
        self.root = Path(fixture["server_path"]).parent.parent
        self.name = fixture["backend_container"]
        self.api = fixture["api_url"]
        if urlparse(self.api).hostname != "127.0.0.1":
            raise ValueError("A local owned fixture is required")
        self.port = urlparse(fixture["base_url"]).port
        self.labels = {"io.mc-admin.e2e.run": fixture["run_id"], "io.mc-admin.e2e.environment": fixture["environment_id"]}
        self.inspect()
        self.requests = 0

    def docker(self, *args):
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=180, check=False)
        if result.returncode:
            raise RuntimeError("Owned Docker command failed: " + args[0])
        return result.stdout + result.stderr if args[0] == "logs" else result.stdout

    def inspect(self):
        value = json.loads(self.docker("inspect", self.name))[0]
        if any(value["Config"]["Labels"].get(key) != expected for key, expected in self.labels.items()):
            raise RuntimeError("Container ownership changed")
        return value

    def request(self, method, path, data=None, *, body=None, headers=None, expected=200, raw=False) -> Any:
        actual_headers = {"Authorization": "Bearer " + self.fixture["master_token"], **(headers or {})}
        if data is not None:
            body = json.dumps(data).encode()
            actual_headers["Content-Type"] = "application/json"
        request = Request(self.api + path, data=body, headers=actual_headers, method=method)
        self.requests += 1
        try:
            response = urlopen(request, timeout=180)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            if response.status != expected:
                raise AssertionError(f"{method} {path}: HTTP {response.status}, expected {expected}")
        return content if raw else json.loads(content) if content else None

    def wait(self, action, *, seconds=40):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                value = action()
                if value:
                    return value
            except (URLError, TimeoutError, AssertionError):
                pass
            time.sleep(0.25)
        raise AssertionError("Timed out waiting for real deployed state")

    def stop(self):
        value = self.inspect()
        self.docker("stop", "--time", "20", value["Id"])
        if self.inspect()["State"]["Running"]:
            raise AssertionError("Owned application did not stop")

    def replace(self, image, *, persistent_root=None, ready=True):
        root = persistent_root or self.root
        exact = self.docker("image", "inspect", image, "--format", "{{.Id}}").strip()
        self.stop()
        self.docker("rm", self.inspect()["Id"])
        args = ["create", "--name", self.name]
        for key, value in self.labels.items():
            args += ["--label", key + "=" + value]
        args += ["--env-file", str(root / "deployment.env"), "--publish", f"127.0.0.1:{self.port}:8000", "--pid", "host"]
        for source, target, suffix in [
            ("/var/run/docker.sock", "/var/run/docker.sock", ""),
            (str(root), "/data", ""),
            (str(root / "servers"), str(self.root / "servers"), ""),
            ("/sys/fs/cgroup", "/cgroup", ",readonly"),
        ]:
            args += ["--mount", "type=bind,src=" + source + ",dst=" + target + suffix]
        self.docker(*args, exact)
        self.docker("start", self.inspect()["Id"])
        if ready:
            self.wait(lambda: self.request("GET", "/admin/users"))
        return exact

    def content(self, path, value=None, *, create=False):
        base = "/servers/" + self.server + "/files"
        if create:
            self.request("POST", base + "/create", {"path": str(Path(path).parent), "name": Path(path).name, "type": "file"})
        route = base + "/content?" + urlencode({"path": path})
        if value is not None:
            self.request("POST", route, {"content": value})
        return self.request("GET", route)["content"]

    def snapshot(self):
        return self.request("POST", "/snapshots", {"server_id": self.server, "paths": ["/world"]})["snapshot"]["id"]

    def stream(self, path, data=None):
        body = self.request("POST", path, data, raw=True)
        events = [json.loads(line[5:].strip()) for line in body.decode().splitlines() if line.startswith("data:")]
        if not events or events[-1].get("event_type") != "complete":
            raise AssertionError("Finite restore did not complete")
        return events[-1]

    def append(self, *lines):
        path = Path(self.fixture["server_path"]) / "data/logs/latest.log"
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise RuntimeError("Player log escaped owned fixture")
        with path.open("a") as stream:
            stream.write("\n" + "\n".join(lines) + "\n")

    def game_ready(self):
        name = "mc-" + self.server
        value = json.loads(self.docker("inspect", name))[0]
        if any(value["Config"]["Labels"].get(key) != expected for key, expected in self.labels.items()):
            raise RuntimeError("Minecraft ownership changed")
        if value["State"].get("Health", {}).get("Status") != "healthy":
            return False
        return bool(self.docker("exec", value["Id"], "rcon-cli", "list").strip())

    def application_source(self):
        code = "from pathlib import Path;import hashlib;r=Path('/app/app');h=hashlib.sha256();[(h.update(str(p.relative_to(r)).encode()+b'\\0'),h.update(p.read_bytes())) for p in sorted(r.rglob('*.py'))];print(h.hexdigest())"
        return self.docker("exec", self.inspect()["Id"], "python", "-c", code).strip()


def database_evidence(root):
    result = {}
    with closing(sqlite3.connect((root / "db.sqlite3").as_uri() + "?mode=ro", uri=True)) as connection, connection:
        result["revision"] = connection.execute("select version_num from alembic_version").fetchone()[0]
        tables = [row[0] for row in connection.execute("select name from sqlite_master where type='table' order by name")]
        for table in tables:
            safe_name = '"' + table.replace('"', '""') + '"'
            rows = connection.execute("select * from " + safe_name).fetchall()
            encoded = sorted(json.dumps(row, default=lambda value: value.hex(), sort_keys=True) for row in rows)
            result[table] = {"rows": len(rows), "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest()}
    return result


def file_evidence(root):
    result = {}
    for selected in [root / "config.toml", root / "servers", root / "archives", root / "restic"]:
        paths = sorted(selected.rglob("*")) if selected.is_dir() else [selected]
        for path in paths:
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as stream:
                    result[str(path.relative_to(root))] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"files": len(result), "sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()}


def seed_player(deployment):
    uuid = "123e4567-e89b-42d3-a456-426614174000"
    deployment.content("/usercache.json", json.dumps([{"name": "ReleaseFixture", "uuid": uuid}]))

    deployment.append(
        f"[12:00:00] [Server thread/INFO]: UUID of player ReleaseFixture is {uuid}",
        "[12:00:01] [Server thread/INFO]: ReleaseFixture[/127.0.0.1:1234] logged in with entity id 1",
        "[12:00:02] [Server thread/INFO]: <ReleaseFixture> retained release chat",
        "[12:00:03] [Server thread/INFO]: ReleaseFixture has made the advancement [Stone Age]",
        "[12:00:04] [Server thread/INFO]: ReleaseFixture lost connection: rehearsal",
    )
    player = deployment.wait(lambda: deployment.request("GET", "/players/uuid/" + uuid.replace("-", "")))
    base = "/players/" + str(player["player_db_id"])
    chat = deployment.wait(lambda: deployment.request("GET", base + "/chat"))
    def closed_sessions():
        rows = deployment.request("GET", base + "/sessions")
        return rows if rows and not any(row["is_active"] for row in rows) else None

    sessions = deployment.wait(closed_sessions)
    achievements = deployment.wait(lambda: deployment.request("GET", base + "/achievements"))
    return {"uuid": uuid.replace("-", ""), "id": player["player_db_id"], "chat": chat, "sessions": sessions, "achievements": achievements}


def archive(deployment, name, value):
    digest = hashlib.sha256(value).hexdigest()
    created = deployment.request("POST", "/archive/upload/init", {"filename": name, "size": len(value)})
    route = "/archive/upload/" + created["upload_id"]
    deployment.request("PATCH", route, body=value, headers={"Upload-Offset": "0", "Content-Type": "application/octet-stream"})
    events = deployment.request("GET", route + "/sha256/stream", raw=True)
    computed = [json.loads(line[5:].strip()) for line in events.decode().splitlines() if line.startswith("data:")][-1]
    assert computed["event_type"] == "complete" and computed["sha256"] == digest
    deployment.request("POST", route + "/verify", {"sha256": digest})
    assert deployment.request("GET", "/archive/download?" + urlencode({"path": "/" + name}), raw=True) == value
    return digest


@contextmanager
def owned_checkpoints(deployment):
    directory = Path(tempfile.mkdtemp(prefix=".rehearsal-checkpoints-", dir=deployment.root))
    try:
        yield directory
    finally:
        deployment.stop()
        shutil.rmtree(directory)


def copy_persistent(deployment, target, checkpoints):
    shutil.copytree(deployment.root, target, symlinks=True, ignore=lambda directory, names: [checkpoints.name] if Path(directory) == deployment.root else [])


def check_retained(deployment, retained, *, upgraded=False):
    base = "/servers/" + deployment.server
    schedule = deployment.request("GET", base + "/restart-schedule")
    assert schedule["cronjob_id"] == retained["schedule"] and schedule["status"] == "paused"
    template = deployment.request("GET", "/templates/" + str(retained["template"]))
    assert template["description"] == "retained released template"
    users = {user["id"]: user for user in deployment.request("GET", "/admin/users")}
    for user in retained["users"]:
        assert {key: users[user["id"]][key] for key in user} == user
    assert deployment.request("GET", "/config/modules/log_parser")["config_data"]["chat_pattern"] == retained["parser_pattern"]
    player = retained["player"]
    detail = deployment.request("GET", "/players/uuid/" + player["uuid"])
    assert detail["player_db_id"] == player["id"]
    for suffix in ["chat", "sessions", "achievements"]:
        current = deployment.request("GET", "/players/" + str(player["id"]) + "/" + suffix)
        assert current == player[suffix], "Historical player IDs/content changed: " + suffix
    snapshots = deployment.request("GET", "/snapshots?" + urlencode({"server_id": deployment.server, "path": "/world"}))["snapshots"]
    assert retained["snapshot"] in {item["id"] for item in snapshots}
    assert deployment.content("/world/release-marker.txt") == ("after upgrade" if upgraded else "release world")
    published = deployment.request("GET", "/archive/download?path=/release.zip", raw=True)
    assert hashlib.sha256(published).hexdigest() == retained["archive"]
    assert deployment.content("/release-data.txt") == "ordinary released data"
    if upgraded:
        assert deployment.content("/new-after-upgrade.txt") == "must survive code rollback"
        assert retained["new_snapshot"] in {item["id"] for item in snapshots}
        operations = deployment.request("GET", "/operations?limit=100")
        rows = operations if isinstance(operations, list) else operations["operations"]
        assert retained["operation"] in {item["operation_id"] for item in rows}
        assert deployment.request("GET", "/cron/post-upgrade-plan")["status"] == "paused"
        assert any(user["username"] == "post-upgrade-user" for user in deployment.request("GET", "/admin/users"))


def run(args, fixture):
    deployment = Deployment(fixture)
    report: dict[str, Any] = {"run_id": fixture["run_id"], "environment_id": fixture["environment_id"], "release_image": fixture["image_id"], "steps": []}
    report["rehearsal_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["release_application_sha256"] = deployment.application_source()
    parser_config = deployment.request("GET", "/config/modules/log_parser")["config_data"]
    parser_config["chat_pattern"] = "(?:)" + parser_config["chat_pattern"]
    deployment.request("PUT", "/config/modules/log_parser", {"config_data": parser_config})
    deployment.request("POST", "/servers/" + deployment.server + "/operations", {"action": "up"})
    deployment.wait(deployment.game_ready, seconds=180)
    print("Released Minecraft fixture is healthy; preparing persistent histories", flush=True)
    retained: dict[str, Any] = {"player": seed_player(deployment)}
    retained["users"] = [{key: user[key] for key in ("id", "username", "role")} for user in deployment.request("GET", "/admin/users")]
    retained["parser_pattern"] = parser_config["chat_pattern"]
    deployment.request("POST", "/servers/" + deployment.server + "/operations", {"action": "down"})
    deployment.content("/release-data.txt", "ordinary released data", create=True)
    deployment.content("/world/release-marker.txt", "release world", create=True)
    retained["archive"] = archive(deployment, "release.zip", b"retained archive bytes\x00\xff")
    compose_path = next(path for path in Path(fixture["server_path"]).iterdir() if path.name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})
    retained["template"] = deployment.request("POST", "/templates/", {
        "name": "release-template", "description": "retained released template", "yaml_template": compose_path.read_text(), "variable_definitions": [],
    }, expected=201)["id"]
    schedule_path = "/servers/" + deployment.server + "/restart-schedule"
    retained["schedule"] = deployment.request("POST", schedule_path, {"custom_cron": "0 0 1 1 *"})["cronjob_id"]
    deployment.request("POST", schedule_path + "/pause")
    retained["snapshot"] = deployment.snapshot()
    check_retained(deployment, retained)
    deployment.stop()
    report["release_database"] = database_evidence(deployment.root)
    report["release_files"] = file_evidence(deployment.root)
    report["steps"].append("released application created real users, server, player histories, template, paused plan, files, archive and Restic snapshot")
    print("Released persistent checkpoint is ready", flush=True)
    with owned_checkpoints(deployment) as checkpoints:
        copy_persistent(deployment, checkpoints / "released", checkpoints)
        report["candidate_image"] = deployment.replace(args.candidate_image)
        report["candidate_application_sha256"] = deployment.application_source()
        check_retained(deployment, retained)
        deployment.content("/new-after-upgrade.txt", "must survive code rollback", create=True)
        deployment.content("/world/release-marker.txt", "after upgrade")
        deployment.request("POST", "/admin/users", {"username": "post-upgrade-user", "password": fixture["password"], "role": "admin"})
        deployment.request("POST", "/cron/", {"cronjob_id": "post-upgrade-plan", "identifier": "backup", "params": {"enable_forget": False}, "cron": "0 0 1 1 *", "name": "post-upgrade retained plan"})
        deployment.request("POST", "/cron/post-upgrade-plan/pause")
        retained["new_snapshot"] = deployment.snapshot()
        operations = deployment.request("GET", "/operations?limit=100")
        rows = operations if isinstance(operations, list) else operations["operations"]
        retained["operation"] = rows[0]["operation_id"]
        check_retained(deployment, retained, upgraded=True)
        print("Upgrade and post-upgrade data verified through APIs", flush=True)
        deployment.stop()
        report["upgraded_database"] = database_evidence(deployment.root)
        report["upgraded_files"] = file_evidence(deployment.root)
        upgraded_copy = checkpoints / "upgraded-copy"
        copy_persistent(deployment, upgraded_copy, checkpoints)
        before_db, before_files = database_evidence(upgraded_copy), file_evidence(upgraded_copy)
        deployment.replace(fixture["image_id"], persistent_root=upgraded_copy, ready=False)
        deployment.wait(lambda: not deployment.inspect()["State"]["Running"], seconds=30)
        logs = deployment.docker("logs", deployment.inspect()["Id"])
        # Startup diagnostics are not exported because the full log is not a public payload.
        assert "Can't locate revision identified by" in logs or "Can't locate revision" in logs
        assert database_evidence(upgraded_copy) == before_db
        assert file_evidence(upgraded_copy) == before_files
        report["old_code_rollback"] = {"supported": False, "reason": "released Alembic cannot locate upgraded revision", "database_unchanged": True, "persistent_files_unchanged": True, "tested_on_full_upgraded_copy": True}
        report["steps"].append("old code refused upgraded schema without deleting post-upgrade data")
        print("Old-code rejection preserved the complete upgraded copy", flush=True)
        deployment.replace(fixture["image_id"], persistent_root=checkpoints / "released")
        check_retained(deployment, retained)
        deployment.request("GET", "/servers/" + deployment.server + "/files/content?path=/new-after-upgrade.txt", expected=404)
        assert not any(user["username"] == "post-upgrade-user" for user in deployment.request("GET", "/admin/users"))
        assert database_evidence(upgraded_copy) == before_db
        report["checkpoint_disaster_recovery"] = {"old_code_started": True, "released_state_verified_through_api": True, "post_checkpoint_data_absent_as_expected": True, "full_upgraded_copy_retained_during_recovery": True, "automatic_data_merge": False}
        report["steps"].append("old code ran against its full consistent released checkpoint; later data was absent there and retained in the separate upgraded copy")
        print("Released checkpoint disaster recovery verified", flush=True)
        report["compatible_rollback_image"] = deployment.replace(args.compatible_image)
        report["compatible_application_sha256"] = deployment.application_source()
        check_retained(deployment, retained, upgraded=True)
        report["steps"].append("same-schema historical image replacement retained new files, users, cron, journal and snapshots; world remained after-upgrade content")
        deployment.replace(args.candidate_image)
        check_retained(deployment, retained, upgraded=True)
        base = "/servers/" + deployment.server + "/world-restore"
        restored = deployment.stream(base + "/restore", {"source_snapshot_id": retained["snapshot"], "selection": {"type": "world"}})
        assert deployment.content("/world/release-marker.txt") == "release world"
        rolled = deployment.stream(base + "/restorations/" + restored["restoration_id"] + "/rollback")
        check_retained(deployment, retained, upgraded=True)
        history = deployment.request("GET", base + "/restorations/" + rolled["restoration_id"])
        assert history["status"] == "succeeded" and history["is_rollback"] and history["safety_snapshot_exists"]
        report["world_recovery"] = {"restoration_id": restored["restoration_id"], "rollback_id": rolled["restoration_id"], "new_nonworld_data_retained": True, "explicit_safety_snapshot": True}
        report["steps"].append("explicit world restore and its safety-snapshot rollback changed world bytes without rolling back application data")
    report["public_requests"] = deployment.requests
    report["retained_ids"] = {key: value for key, value in retained.items() if key != "player"}
    report["player_id"] = retained["player"]["id"]
    report["success"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--compatible-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(Path(os.environ["MC_ADMIN_BROWSER_FIXTURE"]).read_text())
    result = run(args, fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("Owned deployment rehearsal passed: " + str(args.output))


if __name__ == "__main__":
    main()
