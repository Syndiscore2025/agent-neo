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


class ToolExecutor:
    """Executes agent tool calls against the real filesystem and shell."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.files_written: list[str] = []
        self._embed_model = None   # lazy-loaded sentence-transformers model
        self._embed_index: list[dict] = []  # [{path, chunk, embedding}]
        self._embed_ready = False

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        dispatch = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_dir": self._list_dir,
            "run_command": self._run_command,
            "search_code": self._search_code,
            "web_search": self._web_search,
            "semantic_search": self._semantic_search,
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

        # Try embedding-based search first
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer

            if not self._embed_ready:
                self._build_embedding_index()

            if self._embed_index and self._embed_model:
                q_emb = self._embed_model.encode([query], normalize_embeddings=True)[0]
                scored = []
                for entry in self._embed_index:
                    sim = float(np.dot(q_emb, entry["embedding"]))
                    scored.append((sim, entry))
                scored.sort(key=lambda x: x[0], reverse=True)
                results = []
                for sim, entry in scored[:top_k]:
                    results.append(f"[{entry['path']}] (score={sim:.2f})\n{entry['chunk'][:200]}")
                return "\n---\n".join(results) if results else "[no semantic matches]"
        except ImportError:
            pass  # fall through to keyword fallback
        except Exception as exc:
            logger.warning(f"Semantic search embedding failed: {exc}, falling back to keyword")

        # Fallback: keyword search on the query words
        keywords = [w for w in query.split() if len(w) > 3]
        if not keywords:
            return "[semantic_search: query too short for fallback]"
        fallback_pattern = "|".join(re.escape(k) for k in keywords[:5])
        return self._search_code({"pattern": fallback_pattern})

    def _build_embedding_index(self):
        """Build a chunk-level embedding index over the repo (lazy, one-time)."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Building semantic embedding index…")
            self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            chunks = []
            for fpath in self.repo_path.rglob("*"):
                if not fpath.is_file():
                    continue
                if any(p in fpath.parts for p in _SKIP_DIRS):
                    continue
                if fpath.suffix not in {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".md"}:
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    lines = text.splitlines()
                    rel = str(fpath.relative_to(self.repo_path))
                    for i in range(0, len(lines), 40):
                        chunk = "\n".join(lines[i:i + 40])
                        if chunk.strip():
                            chunks.append({"path": rel, "chunk": chunk})
                except Exception:
                    continue
            if chunks:
                texts = [c["chunk"] for c in chunks]
                embeddings = self._embed_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                for c, emb in zip(chunks, embeddings):
                    c["embedding"] = emb
                self._embed_index = chunks
                logger.info(f"Embedding index built: {len(chunks)} chunks")
            self._embed_ready = True
        except Exception as exc:
            logger.warning(f"Could not build embedding index: {exc}")
            self._embed_ready = True  # don't retry

