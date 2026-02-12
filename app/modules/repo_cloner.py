"""
AGENT NEO - Repository Cloner Module

Handles read-only shallow cloning of repositories for calibration.
Never writes to cloned repos. Never pushes. Isolated cache directory.

SECURITY GUARANTEES:
- Read-only operations only
- No git push commands ever
- No force push
- No branch switching on external repos
- Clone URLs with tokens are never logged
- Clones are isolated in CALIBRATION_CACHE_DIR
- No persistent write permissions
"""

import os
import shutil
import subprocess
import logging
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


# Security: List of forbidden git commands
FORBIDDEN_GIT_COMMANDS = [
    "push",
    "push --force",
    "push -f",
    "checkout -b",  # No creating branches on external
    "merge",
    "rebase",
    "reset --hard",
    "clean -fd"
]


def _sanitize_log_url(url: str) -> str:
    """Remove any embedded tokens from URLs for safe logging."""
    # Remove embedded credentials from URL
    # e.g., https://token@github.com -> https://[REDACTED]@github.com
    sanitized = re.sub(
        r"(https?://)[^@]+@",
        r"\1[REDACTED]@",
        url
    )
    return sanitized


@dataclass
class CloneResult:
    """Result of a clone operation."""
    success: bool
    repo_path: Optional[str]
    error: Optional[str] = None
    clone_time_seconds: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "repo_path": self.repo_path,
            "error": self.error,
            "clone_time_seconds": self.clone_time_seconds
        }


@dataclass
class CloneConfig:
    """Configuration for repository cloning."""
    cache_dir: str
    max_clone_time_seconds: int = 120
    cleanup_on_error: bool = True
    
    @classmethod
    def from_env(cls) -> "CloneConfig":
        return cls(
            cache_dir=os.getenv("CALIBRATION_CACHE_DIR", "/opt/agent-neo/calibration"),
            max_clone_time_seconds=int(os.getenv("CALIBRATION_CLONE_TIMEOUT", "120")),
            cleanup_on_error=True
        )


def _get_repo_cache_path(cache_dir: str, full_name: str) -> Path:
    """Generate a deterministic cache path for a repository."""
    # Use hash to avoid path issues with special characters
    name_hash = hashlib.sha256(full_name.encode()).hexdigest()[:12]
    safe_name = full_name.replace("/", "_").replace("\\", "_")
    return Path(cache_dir) / f"{safe_name}_{name_hash}"


def _ensure_cache_dir(cache_dir: str) -> Optional[str]:
    """Ensure cache directory exists and is writable."""
    try:
        path = Path(cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        
        # Verify writable
        test_file = path / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        
        return None
    except Exception as e:
        return f"Cache directory error: {str(e)}"


def _is_directory_dirty(path: Path) -> bool:
    """Check if a cloned repo directory has uncommitted changes."""
    if not path.exists():
        return False
    
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except Exception:
        return True  # Assume dirty on error


def shallow_clone(
    clone_url: str,
    full_name: str,
    default_branch: str,
    config: Optional[CloneConfig] = None,
    use_cache: bool = True
) -> CloneResult:
    """
    Perform a shallow clone of a repository.
    
    Args:
        clone_url: Git clone URL
        full_name: Full repository name (owner/repo)
        default_branch: Default branch to clone
        config: Clone configuration
        use_cache: If True, reuse existing clone if available
        
    Returns:
        CloneResult with success status and path
    """
    if config is None:
        config = CloneConfig.from_env()
    
    start_time = datetime.now()
    
    # Ensure cache directory exists
    cache_error = _ensure_cache_dir(config.cache_dir)
    if cache_error:
        return CloneResult(success=False, repo_path=None, error=cache_error)
    
    repo_path = _get_repo_cache_path(config.cache_dir, full_name)
    
    # Check if cached clone exists
    if use_cache and repo_path.exists():
        if _is_directory_dirty(repo_path):
            logger.warning(f"Cached clone is dirty, removing: {repo_path}")
            cleanup_clone(str(repo_path))
        else:
            # Verify it's a valid git repo
            if (repo_path / ".git").exists():
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Using cached clone: {repo_path}")
                return CloneResult(
                    success=True,
                    repo_path=str(repo_path),
                    clone_time_seconds=elapsed
                )
    
    # Remove existing directory if present
    if repo_path.exists():
        cleanup_clone(str(repo_path))
    
    # Perform shallow clone
    try:
        cmd = [
            "git", "clone",
            "--depth", "1",
            "--branch", default_branch,
            "--single-branch",
            clone_url,
            str(repo_path)
        ]
        
        logger.info(f"Cloning {full_name} (branch: {default_branch})")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.max_clone_time_seconds
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Clone failed"
            if config.cleanup_on_error:
                cleanup_clone(str(repo_path))
            return CloneResult(success=False, repo_path=None, error=error_msg)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Cloned {full_name} in {elapsed:.2f}s")

        return CloneResult(
            success=True,
            repo_path=str(repo_path),
            clone_time_seconds=elapsed
        )

    except subprocess.TimeoutExpired:
        if config.cleanup_on_error:
            cleanup_clone(str(repo_path))
        return CloneResult(
            success=False,
            repo_path=None,
            error=f"Clone timed out after {config.max_clone_time_seconds}s"
        )
    except Exception as e:
        if config.cleanup_on_error:
            cleanup_clone(str(repo_path))
        logger.error(f"Clone error: {e}")
        return CloneResult(success=False, repo_path=None, error=str(e))


def cleanup_clone(repo_path: str) -> bool:
    """
    Remove a cloned repository directory.

    Args:
        repo_path: Path to the cloned repository

    Returns:
        True if cleanup successful
    """
    try:
        path = Path(repo_path)
        if path.exists():
            shutil.rmtree(str(path), ignore_errors=True)
            logger.info(f"Cleaned up clone: {repo_path}")
        return True
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return False


def cleanup_all_clones(cache_dir: Optional[str] = None) -> int:
    """
    Remove all cloned repositories from cache.

    Args:
        cache_dir: Cache directory path (or from env)

    Returns:
        Number of directories removed
    """
    if cache_dir is None:
        cache_dir = os.getenv("CALIBRATION_CACHE_DIR", "/opt/agent-neo/calibration")

    try:
        path = Path(cache_dir)
        if not path.exists():
            return 0

        count = 0
        for item in path.iterdir():
            if item.is_dir() and (item / ".git").exists():
                shutil.rmtree(str(item), ignore_errors=True)
                count += 1

        logger.info(f"Cleaned up {count} cached clones")
        return count
    except Exception as e:
        logger.error(f"Cleanup all error: {e}")
        return 0


def get_cache_status(cache_dir: Optional[str] = None) -> dict:
    """
    Get status of the clone cache.

    Returns:
        Dict with cache statistics
    """
    if cache_dir is None:
        cache_dir = os.getenv("CALIBRATION_CACHE_DIR", "/opt/agent-neo/calibration")

    try:
        path = Path(cache_dir)
        if not path.exists():
            return {
                "exists": False,
                "repo_count": 0,
                "total_size_mb": 0,
                "repos": []
            }

        repos = []
        total_size = 0

        for item in path.iterdir():
            if item.is_dir() and (item / ".git").exists():
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                repos.append({
                    "name": item.name,
                    "size_mb": round(size / (1024 * 1024), 2)
                })
                total_size += size

        return {
            "exists": True,
            "repo_count": len(repos),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "repos": repos
        }
    except Exception as e:
        return {
            "exists": False,
            "error": str(e),
            "repo_count": 0,
            "total_size_mb": 0,
            "repos": []
        }

