from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_health(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_ready(client):
    response = await client.get("/ready")
    payload = response.json()

    assert response.status_code == 200
    assert "models_loaded" in payload
    assert "session_store" in payload
