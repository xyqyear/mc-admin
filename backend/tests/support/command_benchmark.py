"""Run explicitly with python -m tests.support.command_benchmark; owns its server."""

import asyncio
import json
import resource
import statistics
import time
from pathlib import Path

from tests.support.environment import configure_test_environment


async def benchmark(root: Path) -> None:
    from app.minecraft.manager import DockerMCManager
    from app.runtime import Runtime
    from app.utils.exec import exec_command
    from tests.fixtures.test_utils import OwnedDockerResources
    from tests.support.database import initialize_database

    runtime = Runtime()
    resources = OwnedDockerResources(root / "servers")
    with runtime.bind():
        name = resources.name("command-benchmark")
        instance = DockerMCManager(resources.root).get_instance(name)
        try:
            await initialize_database(runtime.database)
            await runtime.config_manager.initialize_all_configs()
            compose = resources.compose(name).replace("EULA: 'true'", "EULA: 'true'\n      ENABLE_QUERY: 'true'")
            await instance.create(compose)
            await instance.up()
            await asyncio.wait_for(instance.wait_until_healthy(), 180)
            assert (await instance.get_server_properties()).enable_query

            async def old_query():
                properties = await instance.get_server_properties()
                config = runtime.dynamic_configuration.players.query
                script = config.query_command.replace("25565", str(properties.query_port))
                return (await exec_command("docker", "compose", "--project-directory", str(instance.get_project_path()),
                                           "exec", "mc", "timeout", str(config.timeout), "bash", "-c", script)).strip()

            async def old_rcon():
                assert await instance.healthy()
                return (await exec_command("docker", "compose", "--project-directory", str(instance.get_project_path()),
                                           "exec", "mc", "rcon-cli", "list")).strip()

            def cpu():
                return sum(value.ru_utime + value.ru_stime for value in (
                    resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN),
                ))

            measurements = {key: [] for key in ("query_old", "query_new", "rcon_old", "rcon_new")}
            cpu_seconds = dict.fromkeys(measurements, 0.0)
            failures = dict.fromkeys(measurements, 0)
            calls = {"query_old": old_query, "query_new": instance.list_players_query,
                     "rcon_old": old_rcon, "rcon_new": lambda: instance.send_command_rcon("list")}
            for round_ in range(100):
                order = list(calls) if round_ % 2 == 0 else list(reversed(calls))
                for key in order:
                    started, used = time.perf_counter(), cpu()
                    try:
                        result = await calls[key]()
                        if key.startswith("query"):
                            assert result in ("", [])
                        else:
                            assert "players" in result
                    except (RuntimeError, TimeoutError, AssertionError):
                        failures[key] += 1
                    finally:
                        measurements[key].append((time.perf_counter() - started) * 1000)
                        cpu_seconds[key] += cpu() - used
            report = {key: {"count": len(values), "first_ms": values[0],
                            "p50_ms": statistics.median(values),
                            "p95_ms": sorted(values)[94], "failures": failures[key],
                            "caller_cpu_seconds": cpu_seconds[key]} for key, values in measurements.items()}
            print(json.dumps(report, indent=2), flush=True)
            Path("/tmp/mc-admin-command-benchmark.json").write_text(json.dumps(report, indent=2))
        finally:
            await runtime.close()
            await resources.cleanup()


if __name__ == "__main__":
    with configure_test_environment() as directory:
        asyncio.run(benchmark(Path(directory)))
