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

