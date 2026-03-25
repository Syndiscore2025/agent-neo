"""
AGENT NEO - Tool Executor
Defines and executes real tools the agent can call (Augment-style).
"""
import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Security blocklist ────────────────────────────────────────────────────────
_BLOCKED = re.compile(
    r"(rm\s+-rf|git\s+push|git\s+reset\s+--hard|sudo|chmod\s+777"
    r"|mkfs|dd\s+if=|curl.*\|\s*sh|wget.*\|\s*sh|>\s*/dev/sd)"
)
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next"}

# ── Anthropic-format tool schemas ─────────────────────────────────────────────
TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read the full content of a file in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write (overwrite) a file with new content. Creates the file if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "content": {"type": "string", "description": "Full file content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_dir",
        "description": "List files and directories at a given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root (default: '.')"}
            },
            "required": []
        }
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the repo root. Use for tests, linters, installs. Never destructive git commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "search_code",
        "description": "Search for a keyword or pattern across all source files in the repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex to search for"},
                "file_glob": {"type": "string", "description": "Optional glob filter like '*.py'"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "finish",
        "description": "Signal task completion. Call when the work is done or no further progress is possible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished"},
                "success": {"type": "boolean", "description": "Whether the task succeeded"}
            },
            "required": ["summary", "success"]
        }
    }
]


class ToolExecutor:
    """Executes agent tool calls against the real filesystem and shell."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.files_written: list[str] = []

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        dispatch = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_dir": self._list_dir,
            "run_command": self._run_command,
            "search_code": self._search_code,
            "finish": lambda inp: f"[finish] {inp.get('summary', '')}",
        }
        fn = dispatch.get(tool_name)
        if not fn:
            return f"[error] Unknown tool: {tool_name}"
        try:
            return fn(tool_input)
        except Exception as exc:
            logger.error(f"Tool {tool_name} raised: {exc}", exc_info=True)
            return f"[error] {tool_name} failed: {exc}"

    # ── individual tool implementations ──────────────────────────────────────

    def _read_file(self, inp: dict) -> str:
        rel = inp["path"].lstrip("/\\")
        full = self.repo_path / rel
        if not full.exists():
            return f"[error] File not found: {rel}"
        if full.stat().st_size > 200_000:
            return f"[error] File too large to read (>{200_000} bytes): {rel}"
        return full.read_text(encoding="utf-8", errors="replace")

    def _write_file(self, inp: dict) -> str:
        rel = inp["path"].lstrip("/\\")
        full = self.repo_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(inp["content"], encoding="utf-8")
        self.files_written.append(rel)
        return f"[ok] Written {rel} ({len(inp['content'])} chars)"

    def _list_dir(self, inp: dict) -> str:
        rel = inp.get("path", ".").lstrip("/\\") or "."
        full = self.repo_path / rel
        if not full.exists():
            return f"[error] Path not found: {rel}"
        entries = []
        for item in sorted(full.iterdir()):
            if item.name in _SKIP_DIRS:
                continue
            entries.append(item.name + "/" if item.is_dir() else item.name)
        return "\n".join(entries) if entries else "(empty)"

    def _run_command(self, inp: dict) -> str:
        cmd = inp["command"]
        if _BLOCKED.search(cmd):
            return f"[blocked] Command not allowed for safety: {cmd}"
        timeout = int(inp.get("timeout", 30))
        result = subprocess.run(
            cmd, shell=True, cwd=str(self.repo_path),
            capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout + result.stderr).strip()
        return f"[exit {result.returncode}]\n{out[:3000]}"

    def _search_code(self, inp: dict) -> str:
        pattern = inp["pattern"]
        glob = inp.get("file_glob", "*")
        matches: list[str] = []
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            compiled = re.compile(re.escape(pattern), re.IGNORECASE)

        for fpath in self.repo_path.rglob(glob):
            if not fpath.is_file():
                continue
            if any(p in fpath.parts for p in _SKIP_DIRS):
                continue
            try:
                for i, line in enumerate(fpath.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if compiled.search(line):
                        rel = str(fpath.relative_to(self.repo_path))
                        matches.append(f"{rel}:{i}: {line.strip()[:120]}")
                        if len(matches) >= 50:
                            break
            except Exception:
                continue
            if len(matches) >= 50:
                break
        return "\n".join(matches) if matches else "[no matches]"

