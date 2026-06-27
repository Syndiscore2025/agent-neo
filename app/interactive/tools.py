"""
AGENT NEO - Tool Executor
Defines and executes real tools the agent can call (Augment-style).
"""
import asyncio
import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Any

from app.interactive.change_set import ChangeSet

logger = logging.getLogger(__name__)

# ── Security blocklist ────────────────────────────────────────────────────────
_BLOCKED = re.compile(
    r"(rm\s+-rf|git\s+push|git\s+reset\s+--hard|sudo|chmod\s+777"
    r"|mkfs|dd\s+if=|curl.*\|\s*sh|wget.*\|\s*sh|>\s*/dev/sd)"
)
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next",
    # Dependency / buildpack runtime trees — never walk these. ".heroku" and
    # "site-packages" appear on Heroku-style deploys (incl. DO App Platform).
    ".heroku", "site-packages", ".mypy_cache", ".pytest_cache", ".cache",
}

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
        "name": "delete_file",
        "description": "Delete a file from the repository. Only use when the task explicitly requires removing a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "rename_file",
        "description": "Rename or move a file within the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "old_path": {"type": "string", "description": "Current relative path from repo root"},
                "new_path": {"type": "string", "description": "New relative path from repo root"}
            },
            "required": ["old_path", "new_path"]
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
    },
    {
        "name": "web_search",
        "description": "Search the web for documentation, error messages, or library information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results to return (default 5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "semantic_search",
        "description": "Semantic (meaning-based) search across the codebase. Finds code related to a concept even without exact keyword matches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language description of what to find"},
                "top_k": {"type": "integer", "description": "Number of results (default 8)"}
            },
            "required": ["query"]
        }
    }
]


def get_filtered_schemas(tool_names: list[str]) -> list[dict]:
    """Return only the TOOL_SCHEMAS entries for the named tools."""
    names_set = set(tool_names)
    return [s for s in TOOL_SCHEMAS if s["name"] in names_set]


def get_integration_schemas() -> list[dict]:
    """Tool schemas for ENABLED MCP/CLI integrations (best-effort)."""
    try:
        from app.modules.integrations import get_integrations_registry
        return get_integrations_registry().get_tool_schemas()
    except Exception as exc:
        logger.warning(f"Integration schemas unavailable: {exc}")
        return []


class ToolExecutor:
    """Executes agent tool calls against the real filesystem and shell."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.files_written: list[str] = []
        self.change_set = ChangeSet()

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        dispatch = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "delete_file": self._delete_file,
            "rename_file": self._rename_file,
            "list_dir": self._list_dir,
            "run_command": self._run_command,
            "search_code": self._search_code,
            "web_search": self._web_search,
            "semantic_search": self._semantic_search,
            "finish": lambda inp: f"[finish] {inp.get('summary', '')}",
        }
        fn = dispatch.get(tool_name)
        if not fn:
            # Integration-backed tools (MCP servers / governed CLI tools)
            if tool_name.startswith("mcp__") or tool_name.startswith("cli__"):
                try:
                    from app.modules.integrations import get_integrations_registry
                    return get_integrations_registry().execute_tool(
                        tool_name, tool_input, str(self.repo_path)
                    )
                except Exception as exc:
                    logger.error(f"Integration tool {tool_name} raised: {exc}", exc_info=True)
                    return f"[error] {tool_name} failed: {exc}"
            return f"[error] Unknown tool: {tool_name}"
        try:
            return fn(tool_input)
        except Exception as exc:
            logger.error(f"Tool {tool_name} raised: {exc}", exc_info=True)
            return f"[error] {tool_name} failed: {exc}"

    async def execute_parallel(self, tool_calls: list[dict[str, Any]]) -> list[str]:
        """Execute multiple independent tool calls concurrently."""
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self.execute, tc["name"], tc["input"])
            for tc in tool_calls
        ]
        return list(await asyncio.gather(*tasks))

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
        existed_before = full.exists()
        try:
            old_content = full.read_text(encoding="utf-8", errors="replace") if existed_before else ""
        except Exception:
            old_content = ""
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(inp["content"], encoding="utf-8")
        self.files_written.append(rel)
        self.change_set.record(rel, old_content, inp["content"], existed_before=existed_before)
        return f"[ok] Written {rel} ({len(inp['content'])} chars)"

    def _delete_file(self, inp: dict) -> str:
        rel = inp["path"].lstrip("/\\")
        full = self.repo_path / rel
        if not full.exists():
            return f"[error] File not found: {rel}"
        if not full.is_file():
            return f"[error] Not a file: {rel}"
        old_content = full.read_text(encoding="utf-8", errors="replace")
        full.unlink()
        self.change_set.record_delete(rel, old_content)
        return f"[ok] Deleted {rel}"

    def _rename_file(self, inp: dict) -> str:
        old_rel = inp["old_path"].lstrip("/\\")
        new_rel = inp["new_path"].lstrip("/\\")
        old_full = self.repo_path / old_rel
        new_full = self.repo_path / new_rel
        if not old_full.exists():
            return f"[error] File not found: {old_rel}"
        if not old_full.is_file():
            return f"[error] Not a file: {old_rel}"
        if new_full.exists():
            return f"[error] Target already exists: {new_rel}"
        content = old_full.read_text(encoding="utf-8", errors="replace")
        new_full.parent.mkdir(parents=True, exist_ok=True)
        old_full.rename(new_full)
        self.files_written.append(new_rel)
        self.change_set.record_rename(old_rel, new_rel, content)
        return f"[ok] Renamed {old_rel} -> {new_rel}"

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

    def _web_search(self, inp: dict) -> str:
        query = inp["query"]
        max_results = int(inp.get("max_results", 5))
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        f"**{r.get('title', 'No title')}**\n"
                        f"URL: {r.get('href', '')}\n"
                        f"{r.get('body', '')[:300]}\n"
                    )
            return "\n---\n".join(results) if results else "[no web results found]"
        except ImportError:
            return "[web_search unavailable: install duckduckgo-search]"
        except Exception as exc:
            return f"[web_search error: {exc}]"

    def _semantic_search(self, inp: dict) -> str:
        query = inp["query"]
        top_k = int(inp.get("top_k", 8))

        # Fan out across all managed repos (semantic with keyword fallback inside);
        # results from non-active repos are tagged with their repo name.
        try:
            from app.modules.repo_index import search_across_repos
            results = search_across_repos(query, k=top_k, active_path=str(self.repo_path))
            if results:
                lines = []
                for r in results:
                    tag = "" if r.get("is_active", True) else f" @{r.get('repo_name') or 'repo'}"
                    lines.append(f"[{r['path']}]{tag} ({r['reason']})\n{r['snippet'][:200]}")
                return "\n---\n".join(lines)
        except Exception as exc:
            logger.warning(f"RepoIndex search failed: {exc}, falling back to keyword")

        # Last-resort fallback: regex keyword search on the query words
        keywords = [w for w in query.split() if len(w) > 3]
        if not keywords:
            return "[semantic_search: query too short for fallback]"
        fallback_pattern = "|".join(re.escape(k) for k in keywords[:5])
        return self._search_code({"pattern": fallback_pattern})

