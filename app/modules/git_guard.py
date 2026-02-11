"""
AGENT NEO - Git Guard
Ensures git repository is in safe state before operations.
"""

import subprocess
from typing import List, Tuple
from pathlib import Path
from app.core.contracts import GitState


class GitGuardError(Exception):
    """Raised when git state is unsafe."""
    pass


def _run_git_command(repo_path: str, args: List[str]) -> Tuple[bool, str]:
    """
    Run git command and return result.
    
    Args:
        repo_path: Path to repository
        args: Git command arguments
        
    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def get_current_branch(repo_path: str) -> str:
    """
    Get current git branch.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Branch name
    """
    success, output = _run_git_command(repo_path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if not success:
        raise GitGuardError(f"Failed to get current branch: {output}")
    return output


def is_detached_head(repo_path: str) -> bool:
    """
    Check if repository is in detached HEAD state.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if detached HEAD
    """
    branch = get_current_branch(repo_path)
    return branch == "HEAD"


def is_working_tree_clean(repo_path: str) -> bool:
    """
    Check if working tree is clean.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if clean
    """
    success, output = _run_git_command(repo_path, ['status', '--porcelain'])
    if not success:
        raise GitGuardError(f"Failed to check working tree: {output}")
    return len(output) == 0


def can_reach_remote(repo_path: str) -> bool:
    """
    Check if remote is reachable.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        True if reachable
    """
    success, _ = _run_git_command(repo_path, ['ls-remote', '--exit-code', 'origin'])
    return success


def get_last_commit_info(repo_path: str) -> Tuple[str, str]:
    """
    Get last commit SHA and message.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Tuple of (sha, message)
    """
    success, sha = _run_git_command(repo_path, ['rev-parse', 'HEAD'])
    if not success:
        return "", ""
    
    success, message = _run_git_command(repo_path, ['log', '-1', '--pretty=%s'])
    if not success:
        return sha, ""
    
    return sha, message


def get_git_state(repo_path: str) -> GitState:
    """
    Get current git state.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        GitState object
    """
    branch = get_current_branch(repo_path)
    clean = is_working_tree_clean(repo_path)
    detached = is_detached_head(repo_path)
    remote_reachable = can_reach_remote(repo_path)
    commit_sha, commit_message = get_last_commit_info(repo_path)
    
    return GitState(
        branch=branch,
        clean=clean,
        detached=detached,
        remote_reachable=remote_reachable,
        last_commit_sha=commit_sha,
        last_commit_message=commit_message
    )


def validate_git_state(repo_path: str, require_remote: bool = True):
    """
    Validate git state is safe for operations.

    Args:
        repo_path: Path to repository
        require_remote: Whether to require remote reachability (default True)

    Raises:
        GitGuardError: If state is unsafe
    """
    # Check repository exists
    if not Path(repo_path).exists():
        raise GitGuardError(f"Repository path does not exist: {repo_path}")

    # Check .git directory exists
    git_dir = Path(repo_path) / '.git'
    if not git_dir.exists():
        raise GitGuardError(f"Not a git repository: {repo_path}")

    # Check current branch
    branch = get_current_branch(repo_path)
    if branch != "main":
        raise GitGuardError(f"Not on main branch. Current branch: {branch}")

    # Check for detached HEAD
    if is_detached_head(repo_path):
        raise GitGuardError("Repository is in detached HEAD state")

    # Check working tree is clean
    if not is_working_tree_clean(repo_path):
        raise GitGuardError("Working tree is not clean. Commit or stash changes first.")

    # Check remote is reachable (optional for testing)
    if require_remote and not can_reach_remote(repo_path):
        raise GitGuardError("Cannot reach remote repository")


def get_last_commits(repo_path: str, count: int = 5) -> List[str]:
    """
    Get last N commit messages.
    
    Args:
        repo_path: Path to repository
        count: Number of commits to retrieve
        
    Returns:
        List of commit messages
    """
    success, output = _run_git_command(
        repo_path,
        ['log', f'-{count}', '--pretty=%h %s']
    )
    if not success:
        return []
    
    return output.split('\n') if output else []

