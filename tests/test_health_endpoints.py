"""
AGENT NEO - Health Endpoints Tests
"""

import pytest
import os
import sys
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_repo):
    """Create test client with temp repo."""
    os.environ["REPO_PATH"] = temp_repo
    os.environ["REQUIRE_REMOTE"] = "false"
    os.environ["SKIP_PUSH"] = "true"
    os.environ["AGENT_NEO_TOKEN"] = "test-token-12345"

    # Remove cached modules to force re-initialization
    modules_to_remove = [key for key in sys.modules.keys() if key.startswith('app.')]
    for mod in modules_to_remove:
        del sys.modules[mod]

    from app.main import app

    # Use context manager to properly run lifespan
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup environment variables
    os.environ.pop("SKIP_PUSH", None)
    os.environ.pop("AGENT_NEO_TOKEN", None)


def test_health_endpoint(client):
    """Test legacy /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "branch" in data
    assert "clean" in data
    assert "remote" in data
    assert data["status"] in ["Working", "Broken"]


def test_liveness_probe(client):
    """Test /health/live endpoint."""
    response = client.get("/health/live")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


def test_readiness_probe_ready(client):
    """Test /health/ready endpoint when ready."""
    response = client.get("/health/ready")
    
    # Should be ready if on main branch and clean
    data = response.json()
    
    if response.status_code == 200:
        assert data["status"] == "ready"
        assert data["branch"] == "main"
        assert "timestamp" in data
    else:
        # May be 503 if not ready
        assert response.status_code == 503


def test_root_endpoint_includes_health_endpoints(client):
    """Test root endpoint includes new health endpoints."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "endpoints" in data
    assert "health_live" in data["endpoints"]
    assert "health_ready" in data["endpoints"]
    assert data["endpoints"]["health_live"] == "/health/live"
    assert data["endpoints"]["health_ready"] == "/health/ready"


def test_root_endpoint_includes_calibration_endpoints(client):
    """Test root endpoint includes calibration endpoints."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "endpoints" in data
    assert "calibrate" in data["endpoints"]
    assert "calibrate_apply" in data["endpoints"]
    assert data["endpoints"]["calibrate"] == "/calibrate"
    assert data["endpoints"]["calibrate_apply"] == "/calibrate/apply"


def test_version_updated(client):
    """Test version is updated to 2.1.0."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "2.1.0"

