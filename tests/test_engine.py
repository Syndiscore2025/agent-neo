"""
AGENT NEO - Engine Tests
"""

import pytest
import os
from app.core.engine import Engine
from app.core.contracts import TaskRequest


@pytest.fixture(autouse=True)
def disable_remote_check():
    """Disable remote check and push for all engine tests."""
    os.environ["REQUIRE_REMOTE"] = "false"
    os.environ["SKIP_PUSH"] = "true"
    yield
    os.environ.pop("REQUIRE_REMOTE", None)
    os.environ.pop("SKIP_PUSH", None)


def test_engine_initialization(temp_repo):
    """Test engine initialization."""
    engine = Engine(temp_repo)
    assert engine.repo_path.exists()
    assert len(engine.kernel_rules) > 0


def test_engine_plan_rapid_mode(temp_repo):
    """Test plan generation for RAPID mode."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-1",
        description="Add new feature",
        diff=None
    )
    
    plan = engine.plan(request)
    assert plan.mode == "RAPID"
    assert plan.task_id == "test-1"


def test_engine_plan_critical_mode(temp_repo):
    """Test plan generation for CRITICAL mode."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-2",
        description="Update authentication logic",
        diff=None
    )
    
    plan = engine.plan(request)
    assert plan.mode == "CRITICAL"
    assert "authentication" in plan.critical_keywords_found


def test_engine_execute_no_diff(temp_repo):
    """Test execution fails without diff."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-3",
        description="Add feature",
        diff=None
    )
    
    response = engine.execute(request)
    assert response.status == "Broken"
    assert "No diff provided" in response.error


def test_engine_execute_invalid_diff(temp_repo, invalid_diff):
    """Test execution fails with invalid diff."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-4",
        description="Add feature",
        diff=invalid_diff
    )
    
    response = engine.execute(request)
    assert response.status == "Broken"
    assert response.validation_result is not None
    assert response.validation_result.valid == False


def test_engine_execute_success_rapid(temp_repo, sample_diff):
    """Test successful execution in RAPID mode."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-5",
        description="Add feature",
        diff=sample_diff,
        force=False
    )
    
    response = engine.execute(request)
    assert response.status == "Working"
    assert response.mode == "RAPID"
    assert response.commit_sha is not None
    assert response.rollback_command is not None
    assert "git revert" in response.rollback_command


def test_engine_execute_critical_no_push(temp_repo, sample_diff):
    """Test CRITICAL mode doesn't push without force."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-6",
        description="Update authentication",
        diff=sample_diff,
        force=False
    )
    
    response = engine.execute(request)
    assert response.status == "Working"
    assert response.mode == "CRITICAL"
    assert response.pushed == False


def test_engine_execute_critical_with_force(temp_repo, sample_diff):
    """Test CRITICAL mode pushes with force flag."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-7",
        description="Update authentication",
        diff=sample_diff,
        force=True
    )
    
    response = engine.execute(request)
    assert response.status == "Working"
    assert response.mode == "CRITICAL"
    # Note: push will fail in test because no remote, but that's expected


def test_engine_execute_forbidden_pattern(temp_repo, forbidden_diff):
    """Test execution fails with forbidden patterns."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-8",
        description="Add feature",
        diff=forbidden_diff
    )
    
    response = engine.execute(request)
    assert response.status == "Broken"
    assert len(response.validation_result.forbidden_patterns) > 0


def test_engine_execute_too_large(temp_repo, large_diff):
    """Test execution fails with too large diff."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-9",
        description="Add feature",
        diff=large_diff
    )
    
    response = engine.execute(request)
    assert response.status == "Broken"
    assert "too many lines" in response.error.lower()

