"""API tests for the backend integrations registry and proxy endpoints."""

import os
import sys

import pytest
from fastapi.testclient import TestClient


def _clear_app_modules():
    mods = [name for name in sys.modules if name.startswith("app.")]
    for mod in mods:
        del sys.modules[mod]


@pytest.fixture
def integrations_client(temp_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")
    monkeypatch.setenv("SKIP_PUSH", "true")
    monkeypatch.setenv("AGENT_NEO_TOKEN", "test-token")
    monkeypatch.setenv("INTEGRATIONS_REGISTRY_PATH", str(tmp_path / "integrations.json"))
    _clear_app_modules()
    from app.main import app

    with TestClient(app) as client:
        yield client


def test_integrations_catalog_and_crud(integrations_client):
    headers = {"Authorization": "Bearer test-token"}

    catalog = integrations_client.get("/integrations/catalog", headers=headers)
    assert catalog.status_code == 200
    assert any(item["provider"] == "github" for item in catalog.json())

    create_response = integrations_client.post(
        "/integrations",
        headers=headers,
        json={
            "provider": "github",
            "label": "Primary GitHub",
            "secret": "ghp_secret_123",
            "headers": {"X-Test": "true"},
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["provider"] == "github"
    assert created["secret_configured"] is True
    assert "secret" not in created

    list_response = integrations_client.get("/integrations", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["integrations"]) == 1

    update_response = integrations_client.patch(
        f"/integrations/{created['id']}",
        headers=headers,
        json={
            "provider": "github",
            "label": "Primary GitHub Updated",
            "base_url": "https://api.github.com",
            "auth_type": "bearer",
            "auth_header": "Authorization",
            "auth_scheme": "Bearer",
            "headers": {"X-Test": "updated"},
            "description": "Updated description",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Primary GitHub Updated"
    assert updated["secret_configured"] is True
    assert updated["headers"]["X-Test"] == "updated"

    delete_response = integrations_client.delete(f"/integrations/{created['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_integrations_proxy_forwards_auth_and_query(integrations_client, monkeypatch):
    headers = {"Authorization": "Bearer test-token"}
    create_response = integrations_client.post(
        "/integrations",
        headers=headers,
        json={
            "provider": "github",
            "label": "Primary GitHub",
            "secret": "ghp_secret_123",
        },
    )
    integration_id = create_response.json()["id"]

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b'{"ok": true}'
        headers = {"content-type": "application/json"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, content=None, headers=None):
            captured["method"] = method
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers or {}
            return FakeResponse()

    import app.main as main_mod
    monkeypatch.setattr(main_mod.httpx, "AsyncClient", FakeAsyncClient)

    proxy_response = integrations_client.get(
        f"/integrations/proxy/{integration_id}/repos/Syndiscore2025/agent-neo?ref=main",
        headers=headers,
    )
    assert proxy_response.status_code == 200
    assert proxy_response.json()["ok"] is True
    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.github.com/repos/Syndiscore2025/agent-neo?ref=main"
    assert captured["headers"]["Authorization"] == "Bearer ghp_secret_123"


def test_integrations_update_preserves_existing_base_url_when_provider_changes(integrations_client):
    headers = {"Authorization": "Bearer test-token"}

    create_response = integrations_client.post(
        "/integrations",
        headers=headers,
        json={
            "provider": "custom_api",
            "label": "Custom Service",
            "base_url": "https://example.internal/api",
            "secret": "svc_secret_123",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["base_url"] == "https://example.internal/api"

    update_response = integrations_client.patch(
        f"/integrations/{created['id']}",
        headers=headers,
        json={
            "provider": "github",
            "label": "Custom Service Renamed",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["provider"] == "github"
    assert updated["label"] == "Custom Service Renamed"
    assert updated["base_url"] == "https://example.internal/api"
    assert updated["secret_configured"] is True


def test_integrations_requires_auth(integrations_client):
    response = integrations_client.get("/integrations")
    assert response.status_code == 403 or response.status_code == 401