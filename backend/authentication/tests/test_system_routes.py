from __future__ import annotations


def test_root_endpoint_exposes_service_metadata(api) -> None:
    response = api.root()

    assert response.status_code == 200
    assert response.json() == {
        "service": "Authentication API",
        "version": "1.0.0",
        "status": "ok",
        "docs_url": "/docs",
        "health_url": "/health",
    }


def test_health_endpoint_reports_local_dependency_status(api) -> None:
    response = api.health()

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["service"] == "Authentication API"
    assert payload["providers"]["database"]["configured"] is True
    assert payload["providers"]["email"]["configured"] is False
    assert payload["providers"]["pinecone"]["configured"] is False
