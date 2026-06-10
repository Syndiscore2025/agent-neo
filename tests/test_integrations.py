"""
Tests for the external integrations registry (MCP servers + CLI tools).
"""
import json
import sys

import pytest

from app.modules.integrations import (
    IntegrationsRegistry,
    get_integrations_registry,
    reset_integrations_registry,
)

# Minimal MCP stdio server used to exercise the real JSON-RPC client.
_FAKE_MCP_SERVER = r"""
import json, os, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "serverInfo": {"name": "fake", "version": "1"}}}), flush=True)
    elif method == "tools/list":
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
            "name": "echo", "description": "Echo text back",
            "inputSchema": {"type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"]}}]}}), flush=True)
    elif method == "tools/call":
        text = msg["params"]["arguments"].get("text", "")
        if text == "__env__":
            text = os.environ.get("FAKE_TOKEN", "<unset>")
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": "echo: " + text}]}}), flush=True)
"""


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Isolated NEO_DATA_DIR + fresh singleton per test."""
    d = tmp_path / "neo-data"
    monkeypatch.setenv("NEO_DATA_DIR", str(d))
    reset_integrations_registry()
    yield d
    reset_integrations_registry()


@pytest.fixture
def fake_mcp_script(tmp_path):
    script = tmp_path / "fake_mcp.py"
    script.write_text(_FAKE_MCP_SERVER, encoding="utf-8")
    return str(script)


def _stdio_server(registry, script, **overrides):
    data = {
        "name": "Fake Server",
        "transport": "stdio",
        "command": sys.executable,
        "args": [script],
    }
    data.update(overrides)
    return registry.add_mcp_server(data)


# ── MCP CRUD ──────────────────────────────────────────────────────────────


class TestMcpCrud:
    def test_add_and_list(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "My Server", "transport": "stdio", "command": "npx"})
        assert rec["id"] == "my_server"
        assert rec["enabled"] is True
        assert reg.list_mcp_servers()[0]["name"] == "My Server"

    def test_stdio_requires_command(self, data_dir):
        reg = IntegrationsRegistry()
        with pytest.raises(ValueError):
            reg.add_mcp_server({"name": "x", "transport": "stdio"})

    def test_http_requires_url(self, data_dir):
        reg = IntegrationsRegistry()
        with pytest.raises(ValueError):
            reg.add_mcp_server({"name": "x", "transport": "http"})

    def test_http_server_registers(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server(
            {"name": "Remote", "transport": "http", "url": "https://mcp.example.com/mcp"}
        )
        assert rec["transport"] == "http"
        assert rec["url"] == "https://mcp.example.com/mcp"

    def test_duplicate_names_get_unique_ids(self, data_dir):
        reg = IntegrationsRegistry()
        a = reg.add_mcp_server({"name": "Dup", "command": "a"})
        b = reg.add_mcp_server({"name": "Dup", "command": "b"})
        assert a["id"] != b["id"]

    def test_update_and_disable(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "S", "command": "npx"})
        updated = reg.update_mcp_server(rec["id"], {"enabled": False, "description": "d"})
        assert updated["enabled"] is False
        assert updated["description"] == "d"

    def test_update_unknown_returns_none(self, data_dir):
        reg = IntegrationsRegistry()
        assert reg.update_mcp_server("nope", {"enabled": False}) is None

    def test_remove(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "S", "command": "npx"})
        assert reg.remove_mcp_server(rec["id"]) is True
        assert reg.remove_mcp_server(rec["id"]) is False
        assert reg.list_mcp_servers() == []

    def test_persists_across_restart(self, data_dir):
        reg = IntegrationsRegistry()
        reg.add_mcp_server({"name": "S", "command": "npx"})
        reg2 = IntegrationsRegistry()
        assert reg2.list_mcp_servers()[0]["name"] == "S"


# ── MCP secrets ───────────────────────────────────────────────────────────


class TestMcpSecrets:
    def test_secret_values_never_persisted(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({
            "name": "S", "command": "npx",
            "secret_env": {"API_KEY": "my_secret_ref"},
        })
        assert reg.set_mcp_secrets(rec["id"], {"API_KEY": "hunter2-secret-value"})
        raw = (data_dir / "integrations.json").read_text(encoding="utf-8")
        assert "hunter2-secret-value" not in raw
        assert "my_secret_ref" in raw  # references ARE persisted

    def test_secrets_cached_shows_binding_names_only(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "S", "command": "npx",
                                  "secret_env": {"API_KEY": "ref"}})
        reg.set_mcp_secrets(rec["id"], {"API_KEY": "value"})
        view = reg.get_mcp_server(rec["id"])
        assert view["secrets_cached"] == ["API_KEY"]
        assert "value" not in json.dumps(view)

    def test_secrets_gone_after_restart(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "S", "command": "npx",
                                  "secret_env": {"API_KEY": "ref"}})
        reg.set_mcp_secrets(rec["id"], {"API_KEY": "value"})
        reg2 = IntegrationsRegistry()
        assert reg2.get_mcp_server(rec["id"])["secrets_cached"] == []

    def test_missing_secret_fails_refresh(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        rec = _stdio_server(reg, fake_mcp_script,
                            secret_env={"NEVER_SET_BINDING": "NEVER_SET_REF"})
        result = reg.refresh_mcp_server(rec["id"])
        assert result["last_refresh_ok"] is False
        assert "missing secret" in result["last_refresh_error"]

    def test_secret_injected_into_stdio_env(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        rec = _stdio_server(reg, fake_mcp_script,
                            secret_env={"FAKE_TOKEN": "FAKE_TOKEN_REF"})
        reg.set_mcp_secrets(rec["id"], {"FAKE_TOKEN": "tok-123"})
        reg.refresh_mcp_server(rec["id"])
        out = reg.execute_tool(f"mcp__{rec['id']}__echo", {"text": "__env__"})
        assert "tok-123" in out


# ── MCP discovery + execution (real stdio client) ─────────────────────────


class TestMcpStdio:
    def test_refresh_discovers_tools(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        rec = _stdio_server(reg, fake_mcp_script)
        result = reg.refresh_mcp_server(rec["id"])
        assert result["last_refresh_ok"] is True
        assert result["tools"][0]["name"] == "echo"

    def test_execute_mcp_tool(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        rec = _stdio_server(reg, fake_mcp_script)
        reg.refresh_mcp_server(rec["id"])
        out = reg.execute_tool(f"mcp__{rec['id']}__echo", {"text": "hello"})
        assert out == "echo: hello"

    def test_refresh_bad_command_records_error(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_mcp_server({"name": "Bad", "command": "definitely-not-a-cmd-xyz"})
        result = reg.refresh_mcp_server(rec["id"])
        assert result["last_refresh_ok"] is False
        assert result["last_refresh_error"]

    def test_disabled_server_not_executable(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        rec = _stdio_server(reg, fake_mcp_script)
        reg.refresh_mcp_server(rec["id"])
        reg.update_mcp_server(rec["id"], {"enabled": False})
        out = reg.execute_tool(f"mcp__{rec['id']}__echo", {"text": "x"})
        assert out.startswith("[blocked]")

    def test_unknown_server_returns_error(self, data_dir):
        reg = IntegrationsRegistry()
        out = reg.execute_tool("mcp__nope__echo", {"text": "x"})
        assert out.startswith("[error]")


# ── CLI CRUD ──────────────────────────────────────────────────────────────


class TestCliCrud:
    def test_add_list_update_remove(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        assert rec["available"] is True
        assert reg.list_cli_tools()[0]["id"] == rec["id"]
        updated = reg.update_cli_tool(rec["id"], {"enabled": False})
        assert updated["enabled"] is False
        assert reg.remove_cli_tool(rec["id"]) is True
        assert reg.list_cli_tools() == []

    def test_requires_name_and_executable(self, data_dir):
        reg = IntegrationsRegistry()
        with pytest.raises(ValueError):
            reg.add_cli_tool({"name": "x"})
        with pytest.raises(ValueError):
            reg.add_cli_tool({"executable": "x"})

    def test_unavailable_executable_flagged(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Ghost", "executable": "definitely-not-a-cmd-xyz"})
        assert rec["available"] is False

    def test_timeout_clamped(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "T", "executable": "x", "timeout": 9999})
        assert rec["timeout"] == 300

    def test_persists_across_restart(self, data_dir):
        reg = IntegrationsRegistry()
        reg.add_cli_tool({"name": "P", "executable": sys.executable})
        reg2 = IntegrationsRegistry()
        assert reg2.list_cli_tools()[0]["name"] == "P"


# ── CLI execution (governed) ──────────────────────────────────────────────


class TestCliExecution:
    def test_runs_argv_no_shell(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        out = reg.execute_tool(f"cli__{rec['id']}", {"args": ["-c", "print('hi-cli')"]})
        assert out.startswith("[exit 0]")
        assert "hi-cli" in out

    def test_shell_metacharacters_not_interpreted(self, data_dir, tmp_path):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        marker = tmp_path / "pwned.txt"
        out = reg.execute_tool(
            f"cli__{rec['id']}",
            {"args": ["-c", "import sys; print(sys.argv[1])", f"x > {marker}"]},
        )
        assert not marker.exists()  # redirection is just an argv string

    def test_allowlist_enforced(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Py", "executable": sys.executable,
                                "allowed_subcommands": ["status"]})
        blocked = reg.execute_tool(f"cli__{rec['id']}", {"args": ["push"]})
        assert blocked.startswith("[blocked]")
        ok = reg.execute_tool(f"cli__{rec['id']}", {"args": ["status"]})
        assert not ok.startswith("[blocked]")

    def test_blocked_regex_still_applies(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Git", "executable": "git"})
        out = reg.execute_tool(f"cli__{rec['id']}", {"args": ["push", "origin", "main"]})
        assert out.startswith("[blocked]")

    def test_disabled_tool_not_executable(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable,
                                "enabled": False})
        out = reg.execute_tool(f"cli__{rec['id']}", {"args": ["-c", "print(1)"]})
        assert out.startswith("[blocked]")

    def test_bad_args_rejected(self, data_dir):
        reg = IntegrationsRegistry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        out = reg.execute_tool(f"cli__{rec['id']}", {"args": "not-a-list"})
        assert out.startswith("[error]")

    def test_unknown_tool_returns_error(self, data_dir):
        reg = IntegrationsRegistry()
        assert reg.execute_tool("cli__nope", {"args": []}).startswith("[error]")


# ── agent exposure ────────────────────────────────────────────────────────


class TestAgentExposure:
    def test_schemas_reflect_enabled_state(self, data_dir, fake_mcp_script):
        reg = IntegrationsRegistry()
        mcp = _stdio_server(reg, fake_mcp_script)
        reg.refresh_mcp_server(mcp["id"])
        cli = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        names = [s["name"] for s in reg.get_tool_schemas()]
        assert f"mcp__{mcp['id']}__echo" in names
        assert f"cli__{cli['id']}" in names
        # disable both → no longer exposed
        reg.update_mcp_server(mcp["id"], {"enabled": False})
        reg.update_cli_tool(cli["id"], {"enabled": False})
        assert reg.get_tool_schemas() == []

    def test_schemas_are_anthropic_format(self, data_dir):
        reg = IntegrationsRegistry()
        reg.add_cli_tool({"name": "Python", "executable": sys.executable,
                          "allowed_subcommands": ["run"]})
        schema = reg.get_tool_schemas()[0]
        assert set(schema.keys()) == {"name", "description", "input_schema"}
        assert "run" in schema["description"]  # allowlist surfaced to the model

    def test_tool_executor_routes_integration_tools(self, data_dir, tmp_path):
        from app.interactive.tools import ToolExecutor, get_integration_schemas
        reset_integrations_registry()
        reg = get_integrations_registry()
        rec = reg.add_cli_tool({"name": "Python", "executable": sys.executable})
        executor = ToolExecutor(str(tmp_path))
        out = executor.execute(f"cli__{rec['id']}", {"args": ["-c", "print('routed')"]})
        assert "routed" in out
        assert any(s["name"] == f"cli__{rec['id']}" for s in get_integration_schemas())

    def test_singleton_uses_env_data_dir(self, data_dir):
        reg = get_integrations_registry()
        assert reg.data_dir == data_dir
        assert get_integrations_registry() is reg
