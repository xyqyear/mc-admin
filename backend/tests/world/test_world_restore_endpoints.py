from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import api_app
from app.runtime_resources import current_runtime

pytestmark = pytest.mark.binary("fd")


@pytest.fixture
async def http(tmp_path, monkeypatch):
    data = tmp_path / "srv1" / "data"
    (data / "world" / "region").mkdir(parents=True)
    (data / "world" / "DIM-1" / "region").mkdir(parents=True)
    (data / "world" / "level.dat").write_bytes(b"level-stub")
    (data / "world" / "region" / "r.0.0.mca").write_bytes(bytes(8192))
    (data / "world" / "DIM-1" / "region" / "r.0.0.mca").write_bytes(bytes(8192))
    instance = SimpleNamespace(exists=AsyncMock(return_value=True), get_data_path=lambda: data)
    current_runtime().resources["docker_mc_manager"] = SimpleNamespace(get_instance=lambda name: instance)
    monkeypatch.setattr(get_settings(), "master_token", "layout-test")
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test", headers={"Authorization": "Bearer layout-test"}) as client:
        yield client


@pytest.mark.asyncio
async def test_get_layout_returns_world_roots(http: AsyncClient):
    response = await http.get("/api/servers/srv1/world-restore/layout")
    assert response.status_code == 200
    data = response.json()
    assert "world_roots" in data
    assert len(data["world_roots"]) == 1
    root = data["world_roots"][0]
    assert root["name"] == "world"
    assert len(root["dimensions"]) == 2
    assert all("label" not in d for d in root["dimensions"])


@pytest.mark.asyncio
async def test_get_dimension_labels_returns_dynamic_mapping(http: AsyncClient):
    response = await http.get(
        "/api/servers/srv1/world-restore/dimension-labels"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["dimension_labels"]["."] == "主世界"
    assert data["dimension_labels"]["DIM-1"] == "下界"
