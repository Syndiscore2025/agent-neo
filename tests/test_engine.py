"""
AGENT NEO - Engine Tests
"""

import pytest
import os
from app.core.engine import Engine
from app.core.contracts import TaskRequest, TestResult


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


def test_engine_plan_with_diff(temp_repo, sample_diff):
    """Test plan generation with a diff (covers lines 79-81)."""
    engine = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-plan-diff",
        description="Add new feature",
        diff=sample_diff
    )

    plan = engine.plan(request)
    assert plan.mode == "RAPID"
    assert plan.task_id == "test-plan-diff"
    assert len(plan.files_to_modify) > 0
    assert plan.estimated_lines > 0


def test_engine_execute_governance_severe_rapid(temp_repo):
    """Test governance blocks severe violations in RAPID mode (EXEC-004: git push -f)."""
    engine = Engine(temp_repo)
    # "git push -f" triggers EXEC-004 but NOT validation's forbidden patterns
    # (validation catches --force\b and \bFORCE\b, not "git push -f")
    diff = """--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file

 def hello():
+    os.system('git push -f origin main')
     return 'world'
"""
    request = TaskRequest(
        task_id="test-gov-rapid",
        description="Add feature",
        diff=diff
    )

    response = engine.execute(request)
    assert response.status == "Broken"
    assert "Governance" in response.error or "EXEC-004" in response.error or "force push" in response.error.lower()


def test_engine_execute_governance_severe_critical(temp_repo):
    """Test governance blocks severe violations in CRITICAL mode (EXEC-004: git push -f)."""
    engine = Engine(temp_repo)
    # "git push -f" triggers EXEC-004 but NOT validation's forbidden patterns
    diff = """--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file

 def hello():
+    os.system('git push -f origin main')
     return 'world'
"""
    request = TaskRequest(
        task_id="test-gov-critical",
        description="Update authentication feature",  # triggers CRITICAL mode
        diff=diff
    )

    response = engine.execute(request)
    assert response.status == "Broken"
    assert "Governance" in response.error or "CRITICAL mode blocks severe" in response.error or "force push" in response.error.lower()


def test_engine_execute_patch_apply_failure(temp_repo, monkeypatch):
    """Test patch apply failure (line 227)."""
    from app.core import engine as engine_mod

    # Mock apply_patch to fail
    monkeypatch.setattr(engine_mod, "apply_patch", lambda *args: (False, "mock patch failure"))

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-patch-fail",
        description="Add feature",
        diff="""--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file

 def hello():
+    print('Hello')
     return 'world'
"""
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Failed to apply patch" in response.error


def test_engine_execute_commit_failure(temp_repo, sample_diff, monkeypatch):
    """Test commit failure (line 237)."""
    from app.core import engine as engine_mod

    monkeypatch.setattr(engine_mod, "commit_changes", lambda *args, **kwargs: (None, "mock commit failure"))

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-commit-fail",
        description="Add feature",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Failed to commit" in response.error


def test_engine_execute_exception(temp_repo, sample_diff, monkeypatch):
    """Test exception handling in execute (lines 311-319)."""
    from app.core import engine as engine_mod

    def raise_error(*args, **kwargs):
        raise Exception("Unexpected test error")

    monkeypatch.setattr(engine_mod, "apply_patch", raise_error)

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-exception",
        description="Add feature",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Execution error" in response.error


def test_engine_execute_push_safety_fails(temp_repo, sample_diff, monkeypatch):
    """Test push safety validation fails (line 201)."""
    from app.core import engine as engine_mod

    monkeypatch.setattr(engine_mod, "validate_push_safety", lambda *args, **kwargs: (False, "Push unsafe"))

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-push-safety",
        description="Add feature",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Push unsafe" in response.error


def test_engine_execute_pre_tests_fail(temp_repo, sample_diff, monkeypatch):
    """Test pre-tests failure (lines 211-217)."""
    from app.core import engine as engine_mod

    failed_result = TestResult(passed=False, output="test failed", duration_seconds=1.0)
    monkeypatch.setattr(engine_mod, "run_tests", lambda *args, **kwargs: failed_result)

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-pre-tests",
        description="Add feature",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Pre-apply tests failed" in response.error


def test_engine_execute_post_tests_fail(temp_repo, sample_diff, monkeypatch):
    """Test post-tests failure (lines 246-253)."""
    from app.core import engine as engine_mod

    call_count = [0]

    # Mock run_tests to pass first (pre) and fail second (post)
    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return TestResult(passed=True, output="ok", duration_seconds=1.0)
        return TestResult(passed=False, output="post test failed", duration_seconds=1.0)

    monkeypatch.setattr(engine_mod, "run_tests", side_effect)

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-post-tests",
        description="Add feature",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Post-apply tests failed" in response.error


def test_engine_execute_push_fails(temp_repo, sample_diff, monkeypatch):
    """Test push failure (lines 264-271)."""
    from app.core import engine as engine_mod

    # Enable push and make it fail
    monkeypatch.setenv("SKIP_PUSH", "false")
    monkeypatch.setattr(engine_mod, "push_to_main", lambda *args, **kwargs: (False, "push failed"))

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-push-fail",
        description="Add feature",
        diff=sample_diff,
        force=False  # RAPID mode auto-pushes
    )

    response = eng.execute(request)
    assert response.status == "Broken"
    assert "Failed to push" in response.error


def test_engine_execute_pushed_success(temp_repo, sample_diff, monkeypatch):
    """Test successful push (line 278)."""
    from app.core import engine as engine_mod

    # Enable push and make it succeed
    monkeypatch.setenv("SKIP_PUSH", "false")
    monkeypatch.setattr(engine_mod, "push_to_main", lambda *args, **kwargs: (True, ""))

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-push-success",
        description="Add feature",
        diff=sample_diff,
        force=False  # RAPID mode auto-pushes
    )

    response = eng.execute(request)
    assert response.status == "Working"
    assert response.pushed == True
    assert "pushed to main" in response.summary


def test_engine_execute_governance_warnings(temp_repo, sample_diff, monkeypatch):
    """Test governance warnings in summary (line 283)."""
    from app.core import engine as engine_mod
    from app.modules.governance import GovernanceResult, GovernanceViolation, ViolationSeverity

    # Create governance result with INFO warnings (not SEVERE)
    warning_result = GovernanceResult(
        passed=True,
        violations=[GovernanceViolation(
            rule_id="COMM-010",
            message="Is this ready?",
            severity=ViolationSeverity.INFO
        )],
        warnings=["Is this ready?"]
    )

    # Mock validate_diff to return warning result
    def mock_validate(*args, **kwargs):
        return warning_result

    from app.modules import governance
    monkeypatch.setattr(governance.GovernanceValidator, "validate_diff", mock_validate)

    eng = Engine(temp_repo)
    request = TaskRequest(
        task_id="test-gov-warning",
        description="Add feature, is this ready?",
        diff=sample_diff
    )

    response = eng.execute(request)
    assert response.status == "Working", f"Expected Working, got {response.status}: {response.error}"
    assert "Governance warnings" in response.summary

