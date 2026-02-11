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

