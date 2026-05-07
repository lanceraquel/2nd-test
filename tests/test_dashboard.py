from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_renders():
    client = TestClient(app)
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Atlas Research Pipeline" in response.text
    assert "New Run" in response.text
    assert "Stage Timeline" in response.text
