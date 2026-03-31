"""
AGENT NEO - Workspace Manager
Handles GitHub repo cloning, workspace binding, and git commit/push operations.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceState:
    """Tracks the currently-bound workspace."""
    owner: str = ""
    repo: str = ""
    branch: str = ""
    workspace_path: str = ""
    integration_id: str = ""
    file_count: int = 0
    bound: bool = False


# Module-level singleton — lives for the server process lifetime
_state = WorkspaceState()


def get_workspace_state() -> WorkspaceState:
    return _state


def _run(cmd: list[str], cwd: Optional[str] = None, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
    )


def _count_files(path: Path) -> int:
    try:
        return sum(1 for f in path.rglob("*") if f.is_file() and ".git" not in f.parts)
    except Exception:
        return 0


def bind_workspace(
    owner: str,
    repo: str,
    branch: str,
    token: str,
    integration_id: str,
    cache_dir: Optional[str] = None,
) -> WorkspaceState:
    """
    Clone (or pull) a GitHub repo into a local workspace directory.
    Returns the updated WorkspaceState.
    """
    global _state

    cache_root = Path(cache_dir or os.getenv("WORKSPACE_CACHE_DIR", str(Path.home() / ".agent-neo" / "workspaces")))
    cache_root.mkdir(parents=True, exist_ok=True)

    workspace_path = cache_root / f"{owner}__{repo}"
    clone_url = f"https://{token}@github.com/{owner}/{repo}.git"

    if workspace_path.exists():
        logger.info(f"Workspace exists, pulling latest: {workspace_path}")
        result = _run(["git", "fetch", "--all"], cwd=str(workspace_path))
        if result.returncode != 0:
            logger.warning(f"git fetch failed: {result.stderr}")
        result = _run(["git", "checkout", branch], cwd=str(workspace_path))
        if result.returncode != 0:
            raise RuntimeError(f"git checkout {branch} failed: {result.stderr}")
        result = _run(["git", "pull", "origin", branch], cwd=str(workspace_path))
        if result.returncode != 0:
            logger.warning(f"git pull failed: {result.stderr}")
        # Update remote URL with current token (tokens can rotate)
        _run(["git", "remote", "set-url", "origin", clone_url], cwd=str(workspace_path))
    else:
        logger.info(f"Cloning {owner}/{repo} @ {branch} → {workspace_path}")
        result = _run(["git", "clone", "--depth=1", "--branch", branch, clone_url, str(workspace_path)])
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")

    file_count = _count_files(workspace_path)
    _state = WorkspaceState(
        owner=owner,
        repo=repo,
        branch=branch,
        workspace_path=str(workspace_path),
        integration_id=integration_id,
        file_count=file_count,
        bound=True,
    )
    logger.info(f"Workspace bound: {owner}/{repo} @ {branch} ({file_count} files) → {workspace_path}")
    return _state


def commit_and_push(
    message: str,
    token: str,
) -> dict:
    """
    Stage all changes, commit, and push to GitHub.
    Uses the currently-bound workspace. Returns commit info.
    """
    global _state

    if not _state.bound or not _state.workspace_path:
        raise RuntimeError("No workspace is currently bound. Call /workspace/bind first.")

    wpath = _state.workspace_path
    owner, repo, branch = _state.owner, _state.repo, _state.branch

    # Update remote URL so the push uses the latest token
    clone_url = f"https://{token}@github.com/{owner}/{repo}.git"
    _run(["git", "remote", "set-url", "origin", clone_url], cwd=wpath)

    # Stage all changes
    result = _run(["git", "add", "-A"], cwd=wpath)
    if result.returncode != 0:
        raise RuntimeError(f"git add failed: {result.stderr}")

    # Check if there's anything to commit
    status = _run(["git", "status", "--porcelain"], cwd=wpath)
    if not status.stdout.strip():
        return {"committed": False, "pushed": False, "sha": None, "message": "Nothing to commit — working tree clean."}

    # Commit
    result = _run(["git", "commit", "-m", message,
                   "--author=Agent NEO <agent-neo@coding-matrix.local>"], cwd=wpath)
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")

    # Get commit SHA
    sha_result = _run(["git", "rev-parse", "HEAD"], cwd=wpath)
    sha = sha_result.stdout.strip() if sha_result.returncode == 0 else None

    # Push
    result = _run(["git", "push", "origin", branch], cwd=wpath)
    if result.returncode != 0:
        raise RuntimeError(f"git push failed: {result.stderr}")

    logger.info(f"Committed and pushed {sha} to {owner}/{repo}@{branch}")
    return {"committed": True, "pushed": True, "sha": sha, "message": message}

