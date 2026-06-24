"""
AGENT NEO - Managed Repository Registry

Durable, thread-safe registry of repositories Agent Neo manages:
  - attach an already-local git repo
  - clone a GitHub repo into a user-chosen path (attach instead if it exists)
  - track metadata (id, name, path, remote, branch, last indexed time)
  - record durable run summaries (capped history)

Persisted as JSON under NEO_DATA_DIR (default ~/.agent-neo/):
  repos.json — registry + active repo id
  runs.json  — recent run summaries

Secrets are never persisted here. Clone tokens are injected via git's
environment-based config (GIT_CONFIG_*) so they never appear in argv,
.git/config, logs, or this registry.
"""

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_RUN_HISTORY = 200
_GIT_TIMEOUT = 30
_CLONE_TIMEOUT = 300


def get_data_dir() -> Path:
    """Durable local-disk data dir for Agent Neo (NEO_DATA_DIR overrides)."""
    return Path(os.getenv("NEO_DATA_DIR") or (Path.home() / ".agent-neo"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_credentials(url: str) -> str:
    """Remove any userinfo (tokens/passwords) embedded in a remote URL."""
    return re.sub(r"^(\w+://)[^/@]+@", r"\1", url or "")


def _repo_id(path: str) -> str:
    resolved = str(Path(path).resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]


def _git(args: List[str], cwd: Optional[str] = None,
         env: Optional[dict] = None, timeout: int = _GIT_TIMEOUT):
    """Run a git command; returns (returncode, stdout+stderr)."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=cwd, env=env, timeout=timeout,
            capture_output=True, text=True,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"git {args[0]} timed out after {timeout}s"
    except Exception as exc:
        return 1, str(exc)


def _is_git_repo(path: str) -> bool:
    p = Path(path)
    if not p.is_dir():
        return False
    rc, _ = _git(["rev-parse", "--is-inside-work-tree"], cwd=str(p))
    return rc == 0


def _read_remote_url(path: str) -> Optional[str]:
    rc, out = _git(["remote", "get-url", "origin"], cwd=path)
    return _strip_credentials(out.strip()) if rc == 0 and out.strip() else None


def _read_branch(path: str) -> Optional[str]:
    rc, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    return out.strip() if rc == 0 and out.strip() else None


def _normalize_remote(url: Optional[str]) -> str:
    """Normalize a remote URL for equality checks (credentials/.git/case)."""
    u = _strip_credentials((url or "").strip().lower())
    if u.endswith(".git"):
        u = u[:-4]
    return u.rstrip("/")


class ManagedRepoRegistry:
    """Thread-safe, JSON-backed registry of managed repositories."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self._repos_path = self.data_dir / "repos.json"
        self._runs_path = self.data_dir / "runs.json"
        self._lock = threading.Lock()
        self._repos: Dict[str, dict] = {}
        self._active_repo_id: Optional[str] = None
        self._runs: List[dict] = []
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._repos_path.exists():
                data = json.loads(self._repos_path.read_text(encoding="utf-8"))
                self._repos = data.get("repos", {})
                self._active_repo_id = data.get("active_repo_id")
        except Exception as exc:
            logger.warning(f"Could not load repo registry: {exc}")
            self._repos, self._active_repo_id = {}, None
        try:
            if self._runs_path.exists():
                data = json.loads(self._runs_path.read_text(encoding="utf-8"))
                self._runs = data.get("runs", [])
        except Exception as exc:
            logger.warning(f"Could not load run history: {exc}")
            self._runs = []

    def _save_repos(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._repos_path.write_text(
                json.dumps(
                    {"active_repo_id": self._active_repo_id, "repos": self._repos},
                    indent=1,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Could not persist repo registry: {exc}")

    def _save_runs(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._runs_path.write_text(
                json.dumps({"runs": self._runs[:MAX_RUN_HISTORY]}),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Could not persist run history: {exc}")

    # ── repos ────────────────────────────────────────────────────────────

    def list_repos(self) -> List[dict]:
        with self._lock:
            return [dict(r) for r in self._repos.values()]

    def get_repo(self, repo_id: str) -> Optional[dict]:
        with self._lock:
            r = self._repos.get(repo_id)
            return dict(r) if r else None

    def attach(self, path: str, name: Optional[str] = None) -> dict:
        """
        Register an already-local git repo. Idempotent: re-attaching the same
        path refreshes its metadata instead of duplicating the entry.
        """
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            raise ValueError(f"Path does not exist: {path}")
        if not _is_git_repo(str(resolved)):
            raise ValueError(f"Not a git repository: {path}")

        repo_id = _repo_id(str(resolved))
        with self._lock:
            existing = self._repos.get(repo_id, {})
            record = {
                "id": repo_id,
                "name": name or existing.get("name") or resolved.name,
                "path": str(resolved),
                "remote_url": _read_remote_url(str(resolved)),
                "default_branch": _read_branch(str(resolved)),
                "added_at": existing.get("added_at") or _now(),
                "last_indexed_at": existing.get("last_indexed_at"),
                "last_index_stats": existing.get("last_index_stats"),
            }
            self._repos[repo_id] = record
            if self._active_repo_id is None:
                self._active_repo_id = repo_id
            self._save_repos()
            return dict(record)

    def clone(self, url: str, dest_path: str, name: Optional[str] = None,
              token: Optional[str] = None) -> dict:
        """
        Clone a GitHub repo into dest_path and register it.

        If dest_path already contains a git repo with the same remote, it is
        attached instead of recloned. A non-empty mismatched dir is an error.

        The token (if given) is passed to git via environment-based config —
        never argv, never persisted anywhere.
        """
        clean_url = _strip_credentials((url or "").strip())
        if not clean_url:
            raise ValueError("Repository URL is required")
        dest = Path(dest_path).resolve()

        if dest.exists() and any(dest.iterdir()):
            if _is_git_repo(str(dest)):
                existing_remote = _read_remote_url(str(dest))
                if _normalize_remote(existing_remote) == _normalize_remote(clean_url):
                    logger.info(f"Repo already present at {dest}; attaching instead of recloning")
                    record = self.attach(str(dest), name)
                    record["attached_existing"] = True
                    return record
                raise ValueError(
                    f"Destination {dest} is a git repo with a different remote "
                    f"({existing_remote}); refusing to clone over it"
                )
            raise ValueError(f"Destination {dest} exists and is not empty")

        env = None
        if token:
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            env = os.environ.copy()
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraheader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic}"

        dest.parent.mkdir(parents=True, exist_ok=True)
        rc, out = _git(["clone", clean_url, str(dest)], env=env, timeout=_CLONE_TIMEOUT)
        if rc != 0:
            # never echo the env config; git output for clone does not contain it
            raise ValueError(f"git clone failed: {out.strip()[:500]}")

        record = self.attach(str(dest), name)
        record["attached_existing"] = False
        return record

    # ── active repo ──────────────────────────────────────────────────────

    def set_active(self, repo_id: str) -> dict:
        with self._lock:
            if repo_id not in self._repos:
                raise ValueError(f"Unknown repo id: {repo_id}")
            self._active_repo_id = repo_id
            self._save_repos()
            return dict(self._repos[repo_id])

    def get_active(self) -> Optional[dict]:
        with self._lock:
            if self._active_repo_id and self._active_repo_id in self._repos:
                return dict(self._repos[self._active_repo_id])
            return None

    @property
    def active_repo_id(self) -> Optional[str]:
        return self._active_repo_id

    # ── indexing metadata ────────────────────────────────────────────────

    def mark_indexed(self, repo_id: str, stats: Optional[dict] = None) -> None:
        with self._lock:
            repo = self._repos.get(repo_id)
            if not repo:
                return
            repo["last_indexed_at"] = _now()
            repo["last_index_stats"] = stats
            self._save_repos()

    # ── durable run history ──────────────────────────────────────────────

    def record_run(self, summary: dict) -> None:
        with self._lock:
            self._runs.insert(0, summary)
            self._runs = self._runs[:MAX_RUN_HISTORY]
            self._save_runs()

    def list_runs(self, limit: int = 20) -> List[dict]:
        with self._lock:
            return [dict(r) for r in self._runs[:max(1, limit)]]

    # ── migration / defaulting ───────────────────────────────────────────

    def ensure_default(self, repo_path: str) -> None:
        """
        Startup migration: if the registry is empty and repo_path is a git
        repo, attach it as the initial managed repo and make it active.
        """
        with self._lock:
            empty = not self._repos
        if empty and repo_path and _is_git_repo(repo_path):
            try:
                record = self.attach(repo_path)
                logger.info(f"Auto-attached default repo: {record['path']}")
            except Exception as exc:
                logger.warning(f"Could not auto-attach default repo: {exc}")


class RunRecorder:
    """
    Observes SSE events from a run and finalizes a durable run summary.
    Best-effort: never raises into the stream.
    """

    def __init__(self, registry: "ManagedRepoRegistry", task: str,
                 repo_path: Optional[str], model: Optional[str] = None,
                 mode: str = "auto"):
        self._registry = registry
        self._summary = {
            "task": (task or "")[:300],
            "repo_path": repo_path,
            "repo_id": _repo_id(repo_path) if repo_path else None,
            "model": model,
            "mode": mode,
            "status": "interrupted",
            "files": [],
            "commit": None,
            "pre_run_ref": None,
            "error": None,
            "started_at": _now(),
            "finished_at": None,
        }
        self._files: List[str] = []
        self._done = False

    def observe(self, event: dict) -> None:
        try:
            etype = event.get("type")
            if etype == "tool_end" and event.get("path"):
                if event["path"] not in self._files:
                    self._files.append(event["path"])
            elif etype == "commit":
                self._summary["status"] = "committed"
                self._summary["commit"] = event.get("commit_sha") or event.get("sha")
                self._summary["pre_run_ref"] = event.get("pre_run_ref")
            elif etype == "phased_done":
                if self._summary["status"] != "committed":
                    self._summary["status"] = "completed"
            elif etype == "no_changes":
                self._summary["status"] = "no_changes"
            elif etype == "change_set_blocked":
                self._summary["status"] = "blocked"
            elif etype == "run_halted":
                self._summary["status"] = "halted"
            elif etype == "finish":
                if self._summary["status"] == "interrupted":
                    self._summary["status"] = "finished"
            elif etype == "error":
                self._summary["status"] = "error"
                self._summary["error"] = str(event.get("error", ""))[:300]
        except Exception:
            pass

    def finalize(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._summary["files"] = self._files[:50]
            self._summary["finished_at"] = _now()
            self._registry.record_run(self._summary)
        except Exception as exc:
            logger.warning(f"Could not record run summary: {exc}")


# ── shared instance ──────────────────────────────────────────────────────
_REGISTRY: Optional[ManagedRepoRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_managed_repo_registry() -> ManagedRepoRegistry:
    """Return the process-wide registry instance."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = ManagedRepoRegistry()
        return _REGISTRY


def reset_managed_repo_registry() -> None:
    """Clear the shared instance (intended for tests)."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = None
