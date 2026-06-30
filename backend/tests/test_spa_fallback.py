from fastapi.testclient import TestClient

from app.main import app


def test_spa_fallback_serves_index_html():
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/")

    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()
