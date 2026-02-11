"""
AGENT NEO - Patch & Git Operations
Apply patches and perform git operations safely.
"""

import subprocess
from typing import Tuple, Optional


def _run_git_command(repo_path: str, args: list, input_data: Optional[str] = None) -> Tuple[bool, str]:
    """
    Run git command safely.
    
    Args:
        repo_path: Path to repository
        args: Git command arguments
        input_data: Optional stdin data
        
    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=60
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def apply_patch(repo_path: str, diff: str) -> Tuple[bool, str]:
    """
    Apply unified diff patch using git apply.
    
    Args:
        repo_path: Path to repository
        diff: Unified diff string
        
    Returns:
        Tuple of (success, error_message)
    """
    # First, try with --check to validate
    success, output = _run_git_command(
        repo_path,
        ['apply', '--check', '-'],
        input_data=diff
    )
    
    if not success:
        return False, f"Patch validation failed: {output}"
    
    # Apply the patch
    success, output = _run_git_command(
        repo_path,
        ['apply', '-'],
        input_data=diff
    )
    
    if not success:
        return False, f"Patch apply failed: {output}"
    
    return True, ""


def stage_changes(repo_path: str) -> Tuple[bool, str]:
    """
    Stage all changes (git add -A).
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Tuple of (success, error_message)
    """
    success, output = _run_git_command(repo_path, ['add', '-A'])
    if not success:
        return False, f"Failed to stage changes: {output}"
    return True, ""


def commit_changes(repo_path: str, message: str) -> Tuple[Optional[str], str]:
    """
    Commit staged changes.
    
    Args:
        repo_path: Path to repository
        message: Commit message
        
    Returns:
        Tuple of (commit_sha, error_message)
    """
    # Stage changes first
    success, error = stage_changes(repo_path)
    if not success:
        return None, error
    
    # Commit
    success, output = _run_git_command(repo_path, ['commit', '-m', message])
    if not success:
        return None, f"Failed to commit: {output}"
    
    # Get commit SHA
    success, sha = _run_git_command(repo_path, ['rev-parse', 'HEAD'])
    if not success:
        return None, f"Failed to get commit SHA: {sha}"
    
    return sha, ""


def push_to_main(repo_path: str) -> Tuple[bool, str]:
    """
    Push to main branch (never with --force).
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Tuple of (success, error_message)
    """
    success, output = _run_git_command(repo_path, ['push', 'origin', 'main'])
    if not success:
        return False, f"Failed to push: {output}"
    return True, ""


def reset_to_clean_state(repo_path: str) -> Tuple[bool, str]:
    """
    Reset repository to clean state (emergency rollback).
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Tuple of (success, error_message)
    """
    # Reset to HEAD
    success, output = _run_git_command(repo_path, ['reset', '--hard', 'HEAD'])
    if not success:
        return False, f"Failed to reset: {output}"
    
    # Clean untracked files
    success, output = _run_git_command(repo_path, ['clean', '-fd'])
    if not success:
        return False, f"Failed to clean: {output}"
    
    return True, ""


def generate_rollback_command(commit_sha: str) -> str:
    """
    Generate rollback command for a commit.
    
    Args:
        commit_sha: Commit SHA to revert
        
    Returns:
        Rollback command string
    """
    return f"git revert {commit_sha} --no-edit && git push origin main"

