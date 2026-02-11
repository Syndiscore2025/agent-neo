"""
AGENT NEO - Patch & Git Operations Tests
"""

import pytest
import subprocess
from pathlib import Path
from app.modules.patch_git import (
    apply_patch,
    commit_changes,
    generate_rollback_command,
    reset_to_clean_state
)


def test_apply_valid_patch(temp_repo, sample_diff):
    """Test applying valid patch."""
    success, error = apply_patch(temp_repo, sample_diff)
    assert success == True
    assert error == ""
    
    # Verify file was modified
    test_file = Path(temp_repo) / "test.py"
    content = test_file.read_text()
    assert "print('Hello')" in content


def test_apply_invalid_patch(temp_repo, invalid_diff):
    """Test applying invalid patch fails."""
    success, error = apply_patch(temp_repo, invalid_diff)
    assert success == False
    assert error != ""


def test_commit_changes(temp_repo, sample_diff):
    """Test committing changes."""
    # Apply patch first
    apply_patch(temp_repo, sample_diff)
    
    # Commit
    commit_sha, error = commit_changes(temp_repo, "Test commit")
    assert commit_sha is not None
    assert error == ""
    assert len(commit_sha) == 40  # Git SHA is 40 chars


def test_commit_no_changes(temp_repo):
    """Test committing with no changes."""
    commit_sha, error = commit_changes(temp_repo, "Empty commit")
    # Should fail because nothing to commit
    assert commit_sha is None


def test_generate_rollback_command():
    """Test rollback command generation."""
    cmd = generate_rollback_command("abc123")
    assert "git revert abc123" in cmd
    assert "--no-edit" in cmd
    assert "git push origin main" in cmd


def test_reset_to_clean_state(temp_repo, sample_diff):
    """Test resetting to clean state."""
    # Apply patch but don't commit
    apply_patch(temp_repo, sample_diff)
    
    # Verify file is modified
    test_file = Path(temp_repo) / "test.py"
    content = test_file.read_text()
    assert "print('Hello')" in content
    
    # Reset
    success, error = reset_to_clean_state(temp_repo)
    assert success == True
    
    # Verify file is back to original
    content = test_file.read_text()
    assert "print('Hello')" not in content


def test_apply_patch_with_conflict(temp_repo):
    """Test applying patch that conflicts."""
    # Modify file first
    test_file = Path(temp_repo) / "test.py"
    test_file.write_text("# Completely different content\n")
    subprocess.run(['git', 'add', '.'], cwd=temp_repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'Conflicting change'], cwd=temp_repo, check=True)
    
    # Try to apply original diff
    diff = """--- a/test.py
+++ b/test.py
@@ -1,4 +1,5 @@
 # Test file
 
 def hello():
+    print('Hello')
     return 'world'
"""
    success, error = apply_patch(temp_repo, diff)
    assert success == False


def test_apply_patch_apply_step_failure(temp_repo, monkeypatch):
    """Test apply_patch when check succeeds but apply fails (line 68)."""
    from app.modules import patch_git

    call_count = [0]

    def mock_run(repo_path, args, input_data=None):
        call_count[0] += 1
        if 'apply' in args and '--check' not in args:
            # Fail on actual apply (not the check)
            return False, "apply error"
        return True, ""

    monkeypatch.setattr(patch_git, "_run_git_command", mock_run)

    success, error = patch_git.apply_patch(temp_repo, "fake diff")
    assert success is False
    assert "Patch apply failed" in error


def test_run_git_command_timeout(temp_repo, monkeypatch):
    """Test git command timeout handling."""
    from app.modules import patch_git

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=30)

    monkeypatch.setattr(subprocess, "run", mock_run)

    success, output = patch_git._run_git_command(temp_repo, ['status'])
    assert success is False
    assert "timed out" in output


def test_run_git_command_exception(temp_repo, monkeypatch):
    """Test git command general exception handling."""
    from app.modules import patch_git

    def mock_run(*args, **kwargs):
        raise Exception("Unexpected error")

    monkeypatch.setattr(subprocess, "run", mock_run)

    success, output = patch_git._run_git_command(temp_repo, ['status'])
    assert success is False
    assert "Unexpected error" in output


def test_stage_changes_failure(temp_repo, monkeypatch):
    """Test stage_changes failure handling."""
    from app.modules import patch_git

    monkeypatch.setattr(patch_git, "_run_git_command", lambda *args: (False, "staging error"))

    success, error = patch_git.stage_changes(temp_repo)
    assert success is False
    assert "Failed to stage" in error


def test_commit_changes_stage_failure(temp_repo, monkeypatch):
    """Test commit_changes when staging fails."""
    from app.modules import patch_git

    monkeypatch.setattr(patch_git, "stage_changes", lambda *args: (False, "staging error"))

    sha, error = patch_git.commit_changes(temp_repo, "Test commit")
    assert sha is None
    assert "staging error" in error


def test_commit_changes_sha_failure(temp_repo, sample_diff, monkeypatch):
    """Test commit_changes when getting SHA fails."""
    from app.modules import patch_git

    # Apply patch first
    apply_patch(temp_repo, sample_diff)

    call_count = [0]
    original_run = patch_git._run_git_command

    def mock_run(repo_path, args):
        call_count[0] += 1
        if args[0] == 'rev-parse':
            return False, "sha error"
        return original_run(repo_path, args)

    monkeypatch.setattr(patch_git, "_run_git_command", mock_run)

    sha, error = patch_git.commit_changes(temp_repo, "Test commit")
    assert sha is None
    assert "Failed to get commit SHA" in error


def test_push_to_main_failure(temp_repo, monkeypatch):
    """Test push_to_main failure handling."""
    from app.modules import patch_git

    monkeypatch.setattr(patch_git, "_run_git_command", lambda *args: (False, "push error"))

    success, error = patch_git.push_to_main(temp_repo)
    assert success is False
    assert "Failed to push" in error


def test_push_to_main_success(temp_repo, monkeypatch):
    """Test push_to_main success path (line 131)."""
    from app.modules import patch_git

    monkeypatch.setattr(patch_git, "_run_git_command", lambda *args: (True, ""))

    success, error = patch_git.push_to_main(temp_repo)
    assert success is True
    assert error == ""


def test_reset_to_clean_state_reset_failure(temp_repo, monkeypatch):
    """Test reset_to_clean_state when reset fails."""
    from app.modules import patch_git

    monkeypatch.setattr(patch_git, "_run_git_command", lambda *args: (False, "reset error"))

    success, error = patch_git.reset_to_clean_state(temp_repo)
    assert success is False
    assert "Failed to reset" in error


def test_reset_to_clean_state_clean_failure(temp_repo, monkeypatch):
    """Test reset_to_clean_state when clean fails."""
    from app.modules import patch_git

    call_count = [0]

    def mock_run(repo_path, args):
        call_count[0] += 1
        if args[0] == 'clean':
            return False, "clean error"
        return True, ""

    monkeypatch.setattr(patch_git, "_run_git_command", mock_run)

    success, error = patch_git.reset_to_clean_state(temp_repo)
    assert success is False
    assert "Failed to clean" in error

