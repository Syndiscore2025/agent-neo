"""
AGENT NEO - Git Guard Tests
"""

import pytest
import subprocess
from app.modules.git_guard import (
    get_current_branch,
    is_detached_head,
    is_working_tree_clean,
    get_git_state,
    validate_git_state,
    get_last_commits,
    GitGuardError
)


def test_get_current_branch(temp_repo):
    """Test getting current branch."""
    branch = get_current_branch(temp_repo)
    assert branch == "main"


def test_is_not_detached_head(temp_repo):
    """Test that normal repo is not detached HEAD."""
    assert is_detached_head(temp_repo) == False


def test_is_working_tree_clean(temp_repo):
    """Test clean working tree detection."""
    assert is_working_tree_clean(temp_repo) == True


def test_is_working_tree_dirty(temp_repo):
    """Test dirty working tree detection."""
    # Create a new file
    from pathlib import Path
    new_file = Path(temp_repo) / "new.py"
    new_file.write_text("# New file\n")
    
    assert is_working_tree_clean(temp_repo) == False


def test_get_git_state(temp_repo):
    """Test getting git state."""
    state = get_git_state(temp_repo)
    assert state.branch == "main"
    assert state.clean == True
    assert state.detached == False
    assert state.last_commit_sha != ""


def test_validate_git_state_success(temp_repo):
    """Test successful git state validation."""
    # Should not raise (require_remote=False for test repos without remotes)
    validate_git_state(temp_repo, require_remote=False)


def test_validate_git_state_dirty_tree(temp_repo):
    """Test validation fails on dirty tree."""
    from pathlib import Path
    new_file = Path(temp_repo) / "new.py"
    new_file.write_text("# New file\n")

    with pytest.raises(GitGuardError, match="not clean"):
        validate_git_state(temp_repo, require_remote=False)


def test_validate_git_state_wrong_branch(temp_repo):
    """Test validation fails on wrong branch."""
    # Create and checkout a different branch
    subprocess.run(['git', 'checkout', '-b', 'feature'], cwd=temp_repo, check=True, capture_output=True)

    with pytest.raises(GitGuardError, match="Not on main branch"):
        validate_git_state(temp_repo, require_remote=False)


def test_get_last_commits(temp_repo):
    """Test getting last commits."""
    commits = get_last_commits(temp_repo, count=5)
    assert len(commits) >= 1
    assert "Initial commit" in commits[0]


def test_validate_git_state_invalid_path():
    """Test validation fails on invalid path."""
    with pytest.raises(GitGuardError, match="does not exist"):
        validate_git_state("/nonexistent/path")


def test_validate_git_state_not_git_repo(tmp_path):
    """Test validation fails on non-git directory."""
    with pytest.raises(GitGuardError, match="Not a git repository"):
        validate_git_state(str(tmp_path))


def test_validate_git_state_detached_head(temp_repo):
    """Test validation fails on detached HEAD (caught by branch check)."""
    # Get current commit SHA
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=temp_repo,
        capture_output=True,
        text=True
    )
    commit_sha = result.stdout.strip()

    # Checkout the commit directly (detached HEAD)
    subprocess.run(
        ['git', 'checkout', commit_sha],
        cwd=temp_repo,
        capture_output=True
    )

    # Detached HEAD is caught by branch check (branch == "HEAD")
    with pytest.raises(GitGuardError, match="Not on main branch"):
        validate_git_state(temp_repo, require_remote=False)


def test_is_detached_head_true(temp_repo):
    """Test is_detached_head returns True when in detached HEAD state."""
    # Get current commit SHA
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=temp_repo,
        capture_output=True,
        text=True
    )
    commit_sha = result.stdout.strip()

    # Checkout the commit directly (detached HEAD)
    subprocess.run(
        ['git', 'checkout', commit_sha],
        cwd=temp_repo,
        capture_output=True
    )

    assert is_detached_head(temp_repo) is True


def test_validate_git_state_detached_head_after_branch_check(temp_repo, monkeypatch):
    """Test validation fails on detached HEAD (line 177 coverage)."""
    from app.modules import git_guard

    # Mock get_current_branch to return "main" even in detached HEAD
    monkeypatch.setattr(git_guard, "get_current_branch", lambda x: "main")
    # Mock is_detached_head to return True
    monkeypatch.setattr(git_guard, "is_detached_head", lambda x: True)

    try:
        git_guard.validate_git_state(temp_repo, require_remote=False)
        pytest.fail("Expected GitGuardError to be raised")
    except git_guard.GitGuardError as e:
        assert "detached HEAD" in str(e)


def test_validate_git_state_require_remote(temp_repo):
    """Test validation fails when remote is required but not reachable."""
    # temp_repo has no remote configured
    with pytest.raises(GitGuardError, match="Cannot reach remote"):
        validate_git_state(temp_repo, require_remote=True)


def test_get_current_branch_error(tmp_path):
    """Test get_current_branch raises error on non-git directory."""
    with pytest.raises(GitGuardError, match="Failed to get current branch"):
        get_current_branch(str(tmp_path))


def test_is_working_tree_clean_error(tmp_path):
    """Test is_working_tree_clean raises error on non-git directory."""
    with pytest.raises(GitGuardError, match="Failed to check working tree"):
        is_working_tree_clean(str(tmp_path))


def test_get_last_commits_error(tmp_path):
    """Test get_last_commits returns empty list on error."""
    from app.modules.git_guard import get_last_commits
    commits = get_last_commits(str(tmp_path), count=5)
    assert commits == []


def test_get_last_commit_info_error(tmp_path):
    """Test get_last_commit_info returns empty strings on error."""
    from app.modules.git_guard import get_last_commit_info
    sha, message = get_last_commit_info(str(tmp_path))
    assert sha == ""
    assert message == ""


def test_get_last_commit_info_message_error(temp_repo, monkeypatch):
    """Test get_last_commit_info returns sha but empty message on message fetch error."""
    from app.modules import git_guard

    call_count = [0]
    original_run_git_command = git_guard._run_git_command

    def mock_run_git_command(repo_path, args):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call (rev-parse HEAD) succeeds
            return True, "abc123"
        else:
            # Second call (log -1 --pretty=%s) fails
            return False, "error"

    monkeypatch.setattr(git_guard, "_run_git_command", mock_run_git_command)

    sha, message = git_guard.get_last_commit_info(temp_repo)
    assert sha == "abc123"
    assert message == ""


def test_run_git_command_timeout(temp_repo, monkeypatch):
    """Test git command timeout handling."""
    from app.modules import git_guard

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=30)

    monkeypatch.setattr(subprocess, "run", mock_run)

    success, output = git_guard._run_git_command(temp_repo, ['status'])
    assert success is False
    assert "timed out" in output


def test_run_git_command_exception(temp_repo, monkeypatch):
    """Test git command general exception handling."""
    from app.modules import git_guard

    def mock_run(*args, **kwargs):
        raise Exception("Unexpected error")

    monkeypatch.setattr(subprocess, "run", mock_run)

    success, output = git_guard._run_git_command(temp_repo, ['status'])
    assert success is False
    assert "Unexpected error" in output

