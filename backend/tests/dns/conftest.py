from types import SimpleNamespace

import pytest

from app.dns.manager import SimpleDNSManager
from app.dynamic_config.configs.dns import DNSManagerConfig, DNSPod, Manual
from app.minecraft import DockerMCManager
from app.servers.models import Server, ServerStatus
from tests.dns.fakes import StatefulDNS, StatefulRouter
from tests.fixtures.test_utils import create_mc_server_compose_yaml


@pytest.fixture
async def connectivity(isolated_runtime, db_session_factory, runtime_config):
    async with db_session_factory() as session:
        session.add(Server(server_id="survival", status=ServerStatus.ACTIVE))
        await session.commit()
    await isolated_runtime.config_manager.update_config(
        "dns", DNSManagerConfig(enabled=True, dns=DNSPod(), addresses=[Manual()]).model_dump(),
    )
    configuration = runtime_config.dns
    root = isolated_runtime.settings.server_path

    def write_server(server_id, port, *, compose_name=None):
        directory = root / server_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "docker-compose.yml"
        path.write_text(create_mc_server_compose_yaml(compose_name or server_id, port, port + 10))
        return path

    write_server("survival", 25565)
    manager = SimpleDNSManager(configuration=lambda: configuration, docker_manager=DockerMCManager(root))
    provider, router = StatefulDNS(), StatefulRouter()
    manager._dns_client = provider
    manager._mc_router_client = router
    manager._last_config_hash = manager._calculate_config_hash(configuration)
    try:
        yield SimpleNamespace(manager=manager, provider=provider, router=router, configuration=configuration,
                              db=db_session_factory, write_server=write_server)
    finally:
        await manager.close()
