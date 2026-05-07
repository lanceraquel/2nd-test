from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_mode():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["mode"] in {"mock", "openai"}
