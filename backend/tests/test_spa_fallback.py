from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("path", ["/", "/servers/survival/files", "/settings"])
def test_spa_fallback_serves_index_html(path):
    with closing(TestClient(app, raise_server_exceptions=False)) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


@pytest.mark.parametrize("path", ["/api/missing-endpoint", "/assets/missing.js", "/static/missing.png"])
def test_missing_api_or_static_resource_is_not_a_successful_page(path):
    with closing(TestClient(app, raise_server_exceptions=False)) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert "<!doctype html>" not in response.text.lower()
