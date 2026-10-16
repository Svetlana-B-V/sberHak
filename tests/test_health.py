"""Checks of the public health contract and frontend access."""

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


@pytest.fixture
def client():
    application = create_app(Settings(cors_origins=("http://localhost:5173",)))
    with TestClient(application) as test_client:
        yield test_client


def test_health_contract(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "EduAgent ACR",
        "version": "0.2.0",
    }


def test_frontend_can_read_health(client):
    response = client.get(
        "/api/health", headers={"Origin": "http://localhost:5173"}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_frontend_preflight_succeeds(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unconfigured_origin_has_no_cors_permission(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:9999",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
