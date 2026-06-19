from fastapi.testclient import TestClient

from backend.main import app


def test_system_health_endpoint(monkeypatch) -> None:
    import backend.routes.system_health as health_route

    monkeypatch.setattr(health_route, "_check_ollama", lambda base_url, model: "ok")
    monkeypatch.setattr(health_route.YouTubeService, "validate_credentials", lambda self: True)

    with TestClient(app) as client:
        response = client.get("/system-health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["ollama"] == "ok"
    assert payload["scheduler"] == "ok"
    assert payload["youtube"] == "ok"
    assert payload["model"]
    assert payload["timestamp"]
    assert payload["disk_usage"].endswith("%")
    assert isinstance(payload["free_space_gb"], int)
