"""
AGENT NEO - External Integrations (MCP servers + CLI tools)

Durable JSON registry at NEO_DATA_DIR/integrations.json with two collections:

  mcp_servers — local (stdio) or remote (HTTP) Model Context Protocol servers
                whose discovered tools are exposed to the agent as
                ``mcp__<server>__<tool>``.
  cli_tools   — named, governed CLI executables exposed to the agent as
                ``cli__<id>`` (argv execution, shell=False, allowlists).

Secret values are NEVER persisted here. Records hold secret *references*
(binding name → ref); values are resolved at use time from an in-memory
cache (pushed by the VS Code extension out of SecretStorage) or from the
backend process environment.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.modules.managed_repos import get_data_dir

logger = logging.getLogger(__name__)

_MCP_TIMEOUT = 25
_CLI_MAX_TIMEOUT = 300
_MAX_OUTPUT = 3000
_PROTOCOL_VERSION = "2025-03-26"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    return s[:32] or "item"


def _safe_tool_name(name: str) -> str:
    """Sanitize an MCP tool name into the [A-Za-z0-9_-] charset."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


class IntegrationsRegistry:
    """Thread-safe registry of MCP servers and governed CLI tools."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self._path = self.data_dir / "integrations.json"
        self._lock = threading.RLock()
        self._mcp: Dict[str, dict] = {}
        self._cli: Dict[str, dict] = {}
        # Secret values live here only (never written to disk):
        # server_id → {binding name → value}
        self._secret_cache: Dict[str, Dict[str, str]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._mcp = {r["id"]: r for r in data.get("mcp_servers", []) if r.get("id")}
                self._cli = {r["id"]: r for r in data.get("cli_tools", []) if r.get("id")}
        except Exception as exc:
            logger.warning(f"Could not load integrations registry: {exc}")
            self._mcp, self._cli = {}, {}

    def _save(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {
                        "mcp_servers": list(self._mcp.values()),
                        "cli_tools": list(self._cli.values()),
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Could not persist integrations registry: {exc}")

    def _new_id(self, name: str, existing: Dict[str, dict]) -> str:
        base = _slug(name)
        sid, n = base, 2
        while sid in existing:
            sid = f"{base}_{n}"
            n += 1
        return sid

    # ── MCP servers: CRUD ────────────────────────────────────────────────

    def _mcp_view(self, rec: dict) -> dict:
        """Sanitized record + which secret bindings currently have a cached value."""
        out = dict(rec)
        out["secrets_cached"] = sorted(self._secret_cache.get(rec["id"], {}).keys())
        return out

    def list_mcp_servers(self) -> List[dict]:
        with self._lock:
            return [self._mcp_view(r) for r in self._mcp.values()]

    def get_mcp_server(self, server_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._mcp.get(server_id)
            return self._mcp_view(rec) if rec else None

    def add_mcp_server(self, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        transport = (data.get("transport") or "stdio").strip()
        if transport not in ("stdio", "http"):
            raise ValueError("transport must be 'stdio' or 'http'")
        command = (data.get("command") or "").strip() or None
        url = (data.get("url") or "").strip() or None
        if transport == "stdio" and not command:
            raise ValueError("command is required for stdio servers")
        if transport == "http" and not url:
            raise ValueError("url is required for http servers")
        with self._lock:
            sid = self._new_id(name, self._mcp)
            rec = {
                "id": sid,
                "name": name,
                "transport": transport,
                "command": command,
                "args": [str(a) for a in (data.get("args") or [])],
                "url": url,
                "env": dict(data.get("env") or {}),
                "secret_env": dict(data.get("secret_env") or {}),
                "headers": dict(data.get("headers") or {}),
                "enabled": bool(data.get("enabled", True)),
                "description": data.get("description"),
                "tools": [],
                "last_refresh_at": None,
                "last_refresh_ok": None,
                "last_refresh_error": None,
                "added_at": _now(),
                "updated_at": _now(),
            }
            self._mcp[sid] = rec
            self._save()
            return self._mcp_view(rec)

    def update_mcp_server(self, server_id: str, data: dict) -> Optional[dict]:
        with self._lock:
            rec = self._mcp.get(server_id)
            if not rec:
                return None
            for key in ("name", "transport", "command", "args", "url", "env",
                        "secret_env", "headers", "enabled", "description"):
                if key in data:
                    rec[key] = data[key]
            if rec.get("transport") not in ("stdio", "http"):
                raise ValueError("transport must be 'stdio' or 'http'")
            if rec["transport"] == "stdio" and not rec.get("command"):
                raise ValueError("command is required for stdio servers")
            if rec["transport"] == "http" and not rec.get("url"):
                raise ValueError("url is required for http servers")
            rec["updated_at"] = _now()
            self._save()
            return self._mcp_view(rec)

    def remove_mcp_server(self, server_id: str) -> bool:
        with self._lock:
            if server_id not in self._mcp:
                return False
            del self._mcp[server_id]
            self._secret_cache.pop(server_id, None)
            self._save()
            return True

    def set_mcp_secrets(self, server_id: str, secrets: Dict[str, str]) -> bool:
        """Cache secret values in memory only. Empty value removes a binding."""
        with self._lock:
            if server_id not in self._mcp:
                return False
            cache = self._secret_cache.setdefault(server_id, {})
            for binding, value in (secrets or {}).items():
                if value:
                    cache[binding] = value
                else:
                    cache.pop(binding, None)
            return True

    # ── MCP client (stateless JSON-RPC sessions) ─────────────────────────

    def _resolve_bindings(self, rec: dict) -> Tuple[Dict[str, str], List[str]]:
        """Resolve secret bindings: in-memory cache → backend process env."""
        resolved: Dict[str, str] = {}
        missing: List[str] = []
        with self._lock:
            cache = dict(self._secret_cache.get(rec["id"], {}))
        for binding, ref in (rec.get("secret_env") or {}).items():
            value = cache.get(binding) or os.environ.get(ref or "") or os.environ.get(binding)
            if value:
                resolved[binding] = value
            else:
                missing.append(binding)
        return resolved, missing

    @staticmethod
    def _mcp_messages(method: str, params: dict) -> List[dict]:
        return [
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "agent-neo", "version": "1.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
        ]

    def _rpc(self, rec: dict, method: str, params: dict) -> dict:
        secrets, missing = self._resolve_bindings(rec)
        if missing:
            raise RuntimeError(
                f"missing secret value(s): {', '.join(missing)} "
                "(set via the extension or backend env)"
            )
        if rec["transport"] == "stdio":
            return self._stdio_rpc(rec, method, params, secrets)
        return self._http_rpc(rec, method, params, secrets)

    def _stdio_rpc(self, rec: dict, method: str, params: dict,
                   secrets: Dict[str, str]) -> dict:
        exe = shutil.which(rec["command"]) or rec["command"]
        argv = [exe, *(rec.get("args") or [])]
        env = {**os.environ, **(rec.get("env") or {}), **secrets}
        payload = "\n".join(json.dumps(m) for m in self._mcp_messages(method, params)) + "\n"
        proc = subprocess.run(
            argv, input=payload, capture_output=True, text=True,
            env=env, timeout=_MCP_TIMEOUT, shell=False,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") == 2:
                if "error" in msg:
                    err = msg["error"]
                    raise RuntimeError(str(err.get("message") or err))
                return msg.get("result") or {}
        stderr = (proc.stderr or "").strip()[:200]
        raise RuntimeError(f"no response from MCP server (exit {proc.returncode}): {stderr}")

    def _http_rpc(self, rec: dict, method: str, params: dict,
                  secrets: Dict[str, str]) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(rec.get("headers") or {}),
            **secrets,  # secret bindings for http servers are header values
        }
        msgs = self._mcp_messages(method, params)
        resp_headers, _ = self._http_send(rec["url"], headers, msgs[0])
        session = resp_headers.get("mcp-session-id")
        if session:
            headers["Mcp-Session-Id"] = session
        try:
            self._http_send(rec["url"], headers, msgs[1])  # initialized notification
        except Exception:
            pass  # some servers return 202/4xx for notifications
        _, result = self._http_send(rec["url"], headers, msgs[2])
        if not isinstance(result, dict):
            raise RuntimeError("no parseable response from MCP server")
        if "error" in result:
            err = result["error"]
            raise RuntimeError(str(err.get("message") or err))
        return result.get("result") or {}

    @staticmethod
    def _http_send(url: str, headers: dict, message: dict) -> Tuple[dict, Optional[dict]]:
        req = urllib.request.Request(
            url, data=json.dumps(message).encode("utf-8"),
            headers=headers, method="POST",
        )
        with urllib.request.urlopen(req, timeout=_MCP_TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        if "text/event-stream" in ctype:
            data_lines = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
            for d in reversed(data_lines):
                try:
                    return resp_headers, json.loads(d)
                except Exception:
                    continue
            return resp_headers, None
        if raw.strip():
            try:
                return resp_headers, json.loads(raw)
            except Exception:
                return resp_headers, None
        return resp_headers, None

    # ── MCP discovery / health ───────────────────────────────────────────

    def refresh_mcp_server(self, server_id: str) -> Optional[dict]:
        """Run tools/list against the server; cache schemas + health status."""
        with self._lock:
            rec = self._mcp.get(server_id)
            if not rec:
                return None
            snapshot = dict(rec)
        try:
            result = self._rpc(snapshot, "tools/list", {})
            tools = []
            for t in result.get("tools") or []:
                name = t.get("name")
                if not name:
                    continue
                tools.append({
                    "name": name,
                    "description": (t.get("description") or "")[:500],
                    "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
                })
            ok, error = True, None
        except Exception as exc:
            tools, ok, error = [], False, str(exc)[:300]
        with self._lock:
            rec = self._mcp.get(server_id)
            if not rec:
                return None
            if ok:
                rec["tools"] = tools
            rec["last_refresh_at"] = _now()
            rec["last_refresh_ok"] = ok
            rec["last_refresh_error"] = error
            self._save()
            return self._mcp_view(rec)

    # ── CLI tools: CRUD ──────────────────────────────────────────────────

    def _cli_view(self, rec: dict) -> dict:
        out = dict(rec)
        out["available"] = shutil.which(rec.get("executable") or "") is not None
        return out

    def list_cli_tools(self) -> List[dict]:
        with self._lock:
            return [self._cli_view(r) for r in self._cli.values()]

    def get_cli_tool(self, tool_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._cli.get(tool_id)
            return self._cli_view(rec) if rec else None

    def add_cli_tool(self, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        executable = (data.get("executable") or "").strip()
        if not name:
            raise ValueError("name is required")
        if not executable:
            raise ValueError("executable is required")
        with self._lock:
            tid = self._new_id(name, self._cli)
            rec = {
                "id": tid,
                "name": name,
                "executable": executable,
                "default_args": [str(a) for a in (data.get("default_args") or [])],
                "allowed_subcommands": [str(a) for a in (data.get("allowed_subcommands") or [])],
                "enabled": bool(data.get("enabled", True)),
                "timeout": max(1, min(int(data.get("timeout") or 60), _CLI_MAX_TIMEOUT)),
                "description": data.get("description"),
                "added_at": _now(),
                "updated_at": _now(),
            }
            self._cli[tid] = rec
            self._save()
            return self._cli_view(rec)

    def update_cli_tool(self, tool_id: str, data: dict) -> Optional[dict]:
        with self._lock:
            rec = self._cli.get(tool_id)
            if not rec:
                return None
            for key in ("name", "executable", "default_args", "allowed_subcommands",
                        "enabled", "timeout", "description"):
                if key in data:
                    rec[key] = data[key]
            if not (rec.get("executable") or "").strip():
                raise ValueError("executable is required")
            rec["timeout"] = max(1, min(int(rec.get("timeout") or 60), _CLI_MAX_TIMEOUT))
            rec["updated_at"] = _now()
            self._save()
            return self._cli_view(rec)

    def remove_cli_tool(self, tool_id: str) -> bool:
        with self._lock:
            if tool_id not in self._cli:
                return False
            del self._cli[tool_id]
            self._save()
            return True

    # ── agent-facing tool schemas + execution ────────────────────────────

    def get_tool_schemas(self) -> List[dict]:
        """Anthropic-format schemas for all ENABLED integrations only."""
        with self._lock:
            mcp = [dict(r) for r in self._mcp.values() if r.get("enabled")]
            cli = [dict(r) for r in self._cli.values() if r.get("enabled")]
        schemas: List[dict] = []
        for rec in mcp:
            for t in rec.get("tools") or []:
                name = f"mcp__{rec['id']}__{_safe_tool_name(t['name'])}"
                if len(name) > 64:
                    continue
                schemas.append({
                    "name": name,
                    "description": f"[MCP:{rec['name']}] {t.get('description') or t['name']}"[:1000],
                    "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
                })
        for rec in cli:
            desc = rec.get("description") or f"Run the {rec['name']} CLI."
            if rec.get("allowed_subcommands"):
                desc += f" Allowed subcommands: {', '.join(rec['allowed_subcommands'])}."
            schemas.append({
                "name": f"cli__{rec['id']}",
                "description": (
                    f"[CLI:{rec['name']}] {desc} Executes "
                    f"'{rec['executable']}' with the given args (argv, no shell)."
                )[:1000],
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Arguments passed to the executable",
                        },
                        "timeout": {"type": "integer", "description": "Timeout in seconds"},
                    },
                    "required": ["args"],
                },
            })
        return schemas

    def execute_tool(self, tool_name: str, tool_input: dict,
                     repo_path: Optional[str] = None) -> str:
        """Execute an integration-backed tool call (mcp__* / cli__*)."""
        if tool_name.startswith("cli__"):
            return self._execute_cli(tool_name[len("cli__"):], tool_input or {}, repo_path)
        if tool_name.startswith("mcp__"):
            rest = tool_name[len("mcp__"):]
            server_id, _, t_name = rest.partition("__")
            return self._execute_mcp(server_id, t_name, tool_input or {})
        return f"[error] Unknown integration tool: {tool_name}"

    def _execute_mcp(self, server_id: str, t_name: str, inp: dict) -> str:
        with self._lock:
            rec = self._mcp.get(server_id)
            rec = dict(rec) if rec else None
        if not rec:
            return f"[error] MCP server not found: {server_id}"
        if not rec.get("enabled"):
            return f"[blocked] MCP server disabled: {rec['name']}"
        # Map the sanitized tool name back to the server's original name
        original = next(
            (t["name"] for t in rec.get("tools") or []
             if _safe_tool_name(t["name"]) == t_name),
            t_name,
        )
        try:
            result = self._rpc(rec, "tools/call", {"name": original, "arguments": inp})
        except Exception as exc:
            return f"[error] MCP call failed ({rec['name']}/{original}): {exc}"
        parts = []
        for c in result.get("content") or []:
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            else:
                parts.append(f"[{c.get('type', '?')} content omitted]")
        text = "\n".join(parts).strip() or json.dumps(result)[:_MAX_OUTPUT]
        prefix = "[error] " if result.get("isError") else ""
        return prefix + text[:_MAX_OUTPUT]

    def _execute_cli(self, tool_id: str, inp: dict,
                     repo_path: Optional[str]) -> str:
        with self._lock:
            rec = self._cli.get(tool_id)
            rec = dict(rec) if rec else None
        if not rec:
            return f"[error] CLI tool not found: {tool_id}"
        if not rec.get("enabled"):
            return f"[blocked] CLI tool disabled: {rec['name']}"
        args = inp.get("args") or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return "[error] args must be a list of strings"
        allowed = rec.get("allowed_subcommands") or []
        if allowed:
            first = next((a for a in args if not a.startswith("-")), None)
            if first is None or first not in allowed:
                return (
                    f"[blocked] Subcommand not in allowlist for {rec['name']}. "
                    f"Allowed: {', '.join(allowed)}"
                )
        argv = [rec["executable"], *(rec.get("default_args") or []), *args]
        # Same safety screen as run_command (e.g. blocks `git push`)
        from app.interactive.tools import _BLOCKED
        if _BLOCKED.search(" ".join(argv)):
            return f"[blocked] Command not allowed for safety: {' '.join(argv)}"
        exe = shutil.which(argv[0])
        if not exe:
            return f"[error] Executable not found on PATH: {argv[0]}"
        timeout = max(1, min(int(inp.get("timeout") or rec.get("timeout") or 60), _CLI_MAX_TIMEOUT))
        try:
            result = subprocess.run(
                [exe, *argv[1:]], shell=False, cwd=repo_path or None,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"[error] {rec['name']} timed out after {timeout}s"
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        return f"[exit {result.returncode}]\n{out[:_MAX_OUTPUT]}"


# ── shared instance ──────────────────────────────────────────────────────
_REGISTRY: Optional[IntegrationsRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_integrations_registry() -> IntegrationsRegistry:
    """Return the process-wide integrations registry instance."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = IntegrationsRegistry()
        return _REGISTRY


def reset_integrations_registry() -> None:
    """Clear the shared instance (intended for tests)."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = None
