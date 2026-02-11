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


# ============================================================================
# Error path coverage tests for app/main.py
# ============================================================================

def _clear_app_modules():
    """Clear all app.* modules from sys.modules."""
    mods = [k for k in sys.modules if k.startswith('app.')]
    for m in mods:
        del sys.modules[m]


def test_lifespan_no_repo_path(monkeypatch):
    """Test lifespan fails when REPO_PATH not set (lines 47-48)."""
    _clear_app_modules()
    monkeypatch.delenv("REPO_PATH", raising=False)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")

    from app.main import app

    with pytest.raises(RuntimeError, match="REPO_PATH"):
        with TestClient(app):
            pass


def test_lifespan_engine_init_failure(monkeypatch, temp_repo):
    """Test lifespan fails when engine init fails (lines 56-58)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")

    from app.main import app
    import app.main as main_mod

    def bad_engine(*args, **kwargs):
        raise Exception("Engine init failed")
    monkeypatch.setattr(main_mod, "Engine", bad_engine)

    with pytest.raises(Exception, match="Engine init failed"):
        with TestClient(app):
            pass


def test_lifespan_git_validation_failure(monkeypatch, temp_repo):
    """Test lifespan fails when git validation fails (lines 66-68)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")

    from app.main import app
    from app.modules.git_guard import GitGuardError
    import app.modules.git_guard as git_guard_mod

    def bad_validate(*args, **kwargs):
        raise GitGuardError("Git validation failed")
    monkeypatch.setattr(git_guard_mod, "validate_git_state", bad_validate)

    with pytest.raises(GitGuardError, match="Git validation failed"):
        with TestClient(app):
            pass


def test_global_exception_handler(monkeypatch, temp_repo):
    """Test global exception handler (lines 90-91)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")
    monkeypatch.setenv("AGENT_NEO_TOKEN", "test-token")

    from app.main import app

    @app.get("/test-unhandled-exception")
    async def raise_exception():
        raise ValueError("Test unhandled exception")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-unhandled-exception")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "Broken"
        assert "Test unhandled exception" in data["error"]


def test_health_check_exception(monkeypatch, temp_repo):
    """Test health check exception path (lines 126-128)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")

    from app.main import app
    import app.main as main_mod

    with TestClient(app) as client:
        # Patch on main module where get_git_state is imported
        def bad_git_state(*args, **kwargs):
            raise Exception("Git state error")
        monkeypatch.setattr(main_mod, "get_git_state", bad_git_state)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Broken"
        assert data["branch"] == "unknown"


def test_plan_exception(monkeypatch, temp_repo):
    """Test plan endpoint exception path (lines 154-156)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")
    monkeypatch.setenv("AGENT_NEO_TOKEN", "test-token")

    from app.main import app
    import app.main as main_mod

    with TestClient(app) as client:
        def bad_plan(*args, **kwargs):
            raise Exception("Plan generation error")
        monkeypatch.setattr(main_mod.engine, "plan", bad_plan)

        response = client.post(
            "/plan",
            json={"task_id": "test", "description": "test", "diff": None},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 500
        assert "Plan generation error" in response.json()["detail"]


def test_execute_exception(monkeypatch, temp_repo, sample_diff):
    """Test execute endpoint exception path (lines 196-198)."""
    _clear_app_modules()
    monkeypatch.setenv("REPO_PATH", temp_repo)
    monkeypatch.setenv("REQUIRE_REMOTE", "false")
    monkeypatch.setenv("AGENT_NEO_TOKEN", "test-token")

    from app.main import app
    import app.main as main_mod

    with TestClient(app) as client:
        def bad_execute(*args, **kwargs):
            raise Exception("Execute error")
        monkeypatch.setattr(main_mod.engine, "execute", bad_execute)

        response = client.post(
            "/execute",
            json={"task_id": "test", "description": "test", "diff": sample_diff},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 500
        assert "Execute error" in response.json()["detail"]

