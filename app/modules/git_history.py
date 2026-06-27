"""
AGENT NEO - Git History Ingestion
A lightweight, dependency-free reader that turns `git log` into a queryable
record of commits (message + changed files) so the context engine can answer
"why / when did this change" and use history as a relevance signal.

Best-effort: a missing git binary or a non-repo path yields an empty result,
never an exception.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_COMMITS = 200      # how far back we scan
DEFAULT_LIMIT = 5      # relevant commits surfaced to the agent
_TIMEOUT = 10
_REC = "\x1e"          # record separator between commits
_FLD = "\x1f"          # field separator within a commit header
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "make",
    "fix", "add", "update", "change", "use", "via", "when", "why", "did",
    "code", "file", "files", "your", "you", "are", "was", "will", "can",
}


def _git(repo_path: str, args: List[str]) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo_path,
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except Exception as exc:
        logger.debug(f"git_history: git {args[0]} failed: {exc}")
        return None


def get_recent_commits(repo_path: str, limit: int = MAX_COMMITS) -> List[dict]:
    """Return up to `limit` recent commits as dicts, newest first. Never raises."""
    fmt = _FLD.join(["%H", "%h", "%an", "%ad", "%s"])
    proc = _git(repo_path, [
        "log", f"-n{limit}", "--no-merges", "--date=short",
        f"--pretty=format:{_REC}{fmt}", "--name-only",
    ])
    if proc is None or proc.returncode != 0:
        return []
    commits: List[dict] = []
    for block in proc.stdout.split(_REC):
        block = block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        header = lines[0].split(_FLD)
        if len(header) < 5:
            continue
        files = [ln.strip() for ln in lines[1:] if ln.strip()]
        commits.append({
            "sha": header[0],
            "short_sha": header[1],
            "author": header[2],
            "date": header[3],
            "subject": header[4],
            "files": files,
        })
    return commits


def _keywords(task: str) -> set:
    words = re.split(r"[^a-zA-Z0-9_]+", task.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def find_relevant_commits(
    repo_path: str,
    task: str,
    paths: Optional[List[str]] = None,
    limit: int = DEFAULT_LIMIT,
) -> List[dict]:
    """
    Rank recent commits by relevance to `task` and the candidate `paths`.

    Score = keyword overlap in the subject + a bonus per touched candidate path,
    with a small recency tiebreak. Only commits with a positive score surface,
    each tagged with a human-readable `reason`. Never raises.
    """
    commits = get_recent_commits(repo_path)
    if not commits:
        return []
    kws = _keywords(task)
    path_set = {Path(p).as_posix() for p in (paths or [])}
    scored: List[tuple] = []
    n = len(commits)
    for i, c in enumerate(commits):
        subject_l = c["subject"].lower()
        kw_hits = sum(1 for k in kws if k in subject_l)
        touched = [f for f in c["files"] if Path(f).as_posix() in path_set]
        score = kw_hits * 2 + len(touched) * 3
        if score <= 0:
            continue
        recency = (n - i) / n  # newer commits break ties upward
        bits = []
        if touched:
            shown = ", ".join(Path(t).name for t in touched[:3])
            bits.append(f"touches {shown}")
        if kw_hits:
            bits.append("matches task")
        c = {**c, "reason": "; ".join(bits) or "recent change"}
        scored.append((score + recency, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in scored[:limit]]


def summarize_history(commits: List[dict]) -> str:
    """One-line summary of the surfaced commits for prompt injection."""
    if not commits:
        return ""
    head = f"{len(commits)} relevant commit(s)"
    parts: List[str] = []
    for c in commits[:3]:
        parts.append(f"{c['short_sha']} {c['subject'][:50]} ({c['date']})")
    return f"{head}: " + "; ".join(parts)
