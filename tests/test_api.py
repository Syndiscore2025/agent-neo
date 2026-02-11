"""
AGENT NEO - API Tests
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


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "AGENT NEO"
    assert data["status"] == "Working"


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "branch" in data


def test_plan_endpoint_rapid(client):
    """Test plan endpoint for RAPID mode."""
    response = client.post(
        "/plan",
        json={
            "task_id": "test-1",
            "description": "Add new feature",
            "diff": None
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "RAPID"
    assert data["task_id"] == "test-1"


def test_plan_endpoint_critical(client):
    """Test plan endpoint for CRITICAL mode."""
    response = client.post(
        "/plan",
        json={
            "task_id": "test-2",
            "description": "Update authentication",
            "diff": None
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "CRITICAL"
    assert len(data["critical_keywords_found"]) > 0


def test_execute_endpoint_no_diff(client):
    """Test execute endpoint fails without diff."""
    response = client.post(
        "/execute",
        json={
            "task_id": "test-3",
            "description": "Add feature",
            "diff": None
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 400


def test_execute_endpoint_invalid_diff(client, invalid_diff):
    """Test execute endpoint with invalid diff."""
    response = client.post(
        "/execute",
        json={
            "task_id": "test-4",
            "description": "Add feature",
            "diff": invalid_diff
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Broken"


def test_execute_endpoint_success(client, sample_diff):
    """Test successful execution."""
    response = client.post(
        "/execute",
        json={
            "task_id": "test-5",
            "description": "Add feature",
            "diff": sample_diff,
            "force": False
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Working"
    assert data["commit_sha"] is not None
    assert data["rollback_command"] is not None


def test_execute_endpoint_validation_error(client, large_diff):
    """Test execution with validation error."""
    response = client.post(
        "/execute",
        json={
            "task_id": "test-6",
            "description": "Add feature",
            "diff": large_diff,
            "force": False
        },
        headers={"Authorization": "Bearer test-token-12345"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Broken"
    assert data["validation_result"]["valid"] == False

