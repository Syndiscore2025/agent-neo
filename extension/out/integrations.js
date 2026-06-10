"use strict";
/**
 * AGENT NEO - Integrations Manager
 *
 * Quick-pick flows for managing external integrations:
 *   - MCP servers (local stdio or remote HTTP)
 *   - governed CLI tools (argv execution, allowlists — never a raw shell)
 *
 * Secret values live in VS Code SecretStorage (agentNeo.secret.mcp.<id>.<binding>)
 * and are pushed to the backend's in-memory cache — never persisted server-side.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.IntegrationsManager = void 0;
const vscode = __importStar(require("vscode"));
function mcpSecretName(serverId, binding) {
    return 'mcp.' + serverId + '.' + binding;
}
class IntegrationsManager {
    constructor(apiClient, storage) {
        this.apiClient = apiClient;
        this.storage = storage;
    }
    // ── MCP servers ──────────────────────────────────────────────────────
    /**
     * Entry point: list MCP servers + add actions.
     */
    async manageMcpServers() {
        let servers = [];
        try {
            servers = (await this.apiClient.listMcpServers())?.servers ?? [];
        }
        catch {
            vscode.window.showErrorMessage('Agent NEO backend is unreachable.');
            return;
        }
        const items = servers.map(s => ({
            label: `$(server) ${s.name}`,
            description: (s.enabled ? '' : 'disabled · ') +
                (s.transport === 'http' ? s.url : s.command),
            detail: this.mcpDetail(s),
            server: s,
        }));
        items.push({ label: '$(add) Add local MCP server (command)…', action: 'addStdio' }, { label: '$(globe) Add remote MCP server (HTTP)…', action: 'addHttp' });
        const pick = await vscode.window.showQuickPick(items, {
            placeHolder: 'MCP servers — pick one to manage, or add a new one',
        });
        if (!pick) {
            return;
        }
        if (pick.action === 'addStdio') {
            return this.addMcpServer('stdio');
        }
        if (pick.action === 'addHttp') {
            return this.addMcpServer('http');
        }
        if (pick.server) {
            return this.mcpServerActions(pick.server);
        }
    }
    mcpDetail(s) {
        const parts = [s.transport === 'http' ? 'remote (HTTP)' : 'local (stdio)'];
        const toolCount = (s.tools ?? []).length;
        if (s.last_refresh_ok === true) {
            parts.push(`✓ ${toolCount} tool(s)`);
        }
        else if (s.last_refresh_ok === false) {
            parts.push('✗ ' + (s.last_refresh_error || 'unreachable'));
        }
        else {
            parts.push('not tested yet');
        }
        const bindings = Object.keys(s.secret_env ?? {});
        if (bindings.length) {
            parts.push('secrets: ' + bindings.join(', '));
        }
        return parts.join('  ·  ');
    }
    async addMcpServer(transport) {
        const name = await vscode.window.showInputBox({
            prompt: 'Server name (e.g. GitHub MCP, Filesystem)', ignoreFocusOut: true,
        });
        if (!name) {
            return;
        }
        const body = { name, transport };
        if (transport === 'stdio') {
            const command = await vscode.window.showInputBox({
                prompt: 'Command to launch the server (e.g. npx, uvx, python)',
                ignoreFocusOut: true,
            });
            if (!command) {
                return;
            }
            const args = await vscode.window.showInputBox({
                prompt: 'Arguments (space-separated, optional) — e.g. -y @modelcontextprotocol/server-filesystem .',
                ignoreFocusOut: true,
            });
            body.command = command;
            body.args = (args || '').split(/\s+/).filter(Boolean);
        }
        else {
            const url = await vscode.window.showInputBox({
                prompt: 'Server URL (e.g. https://mcp.example.com/mcp)',
                ignoreFocusOut: true,
            });
            if (!url) {
                return;
            }
            body.url = url;
        }
        let server;
        try {
            server = await this.apiClient.addMcpServer(body);
        }
        catch (err) {
            vscode.window.showErrorMessage('Could not add MCP server: ' +
                (err?.response?.data?.detail || err?.message || err));
            return;
        }
        const binding = await vscode.window.showInputBox({
            prompt: transport === 'stdio'
                ? 'Secret env var name the server needs (optional, e.g. GITHUB_TOKEN)'
                : 'Secret header name the server needs (optional, e.g. Authorization)',
            ignoreFocusOut: true,
        });
        if (binding) {
            await this.setMcpSecret(server, binding.trim());
        }
        const test = await vscode.window.showInformationMessage(`MCP server "${server.name}" added. Test it now to discover its tools?`, 'Test now', 'Later');
        if (test === 'Test now') {
            await this.testMcpServer(server);
        }
    }
    async mcpServerActions(server) {
        const pick = await vscode.window.showQuickPick([
            { label: server.enabled ? '$(circle-slash) Disable' : '$(check) Enable', action: 'toggle' },
            { label: '$(beaker) Test connection / discover tools', action: 'test' },
            { label: '$(key) Set secret…', action: 'secret' },
            { label: '$(trash) Remove', action: 'remove' },
        ], { placeHolder: `${server.name} — ${this.mcpDetail(server)}` });
        if (!pick) {
            return;
        }
        try {
            if (pick.action === 'toggle') {
                await this.apiClient.updateMcpServer(server.id, { enabled: !server.enabled });
                vscode.window.showInformationMessage(`MCP server "${server.name}" ${server.enabled ? 'disabled' : 'enabled'}.`);
            }
            else if (pick.action === 'test') {
                await this.testMcpServer(server);
            }
            else if (pick.action === 'secret') {
                const existing = Object.keys(server.secret_env ?? {});
                const binding = await vscode.window.showInputBox({
                    prompt: 'Binding name (env var for stdio, header for HTTP)',
                    value: existing[0] || '',
                    ignoreFocusOut: true,
                });
                if (binding) {
                    await this.setMcpSecret(server, binding.trim());
                }
            }
            else if (pick.action === 'remove') {
                const confirm = await vscode.window.showWarningMessage(`Remove MCP server "${server.name}"?`, { modal: true }, 'Remove');
                if (confirm !== 'Remove') {
                    return;
                }
                for (const binding of Object.keys(server.secret_env ?? {})) {
                    await this.storage.clearSecret(mcpSecretName(server.id, binding));
                }
                await this.apiClient.removeMcpServer(server.id);
                vscode.window.showInformationMessage(`MCP server "${server.name}" removed.`);
            }
        }
        catch (err) {
            vscode.window.showErrorMessage('MCP action failed: ' +
                (err?.response?.data?.detail || err?.message || err));
        }
    }
    /**
     * Store a secret value in SecretStorage, register the binding on the
     * server record (reference only), and push the value to backend memory.
     */
    async setMcpSecret(server, binding) {
        const value = await vscode.window.showInputBox({
            prompt: `Secret value for ${binding} (stored in VS Code SecretStorage)`,
            password: true,
            ignoreFocusOut: true,
        });
        if (!value) {
            return;
        }
        await this.storage.setSecret(mcpSecretName(server.id, binding), value);
        const secretEnv = { ...(server.secret_env ?? {}), [binding]: binding };
        try {
            await this.apiClient.updateMcpServer(server.id, { secret_env: secretEnv });
            await this.apiClient.setMcpSecrets(server.id, { [binding]: value });
            vscode.window.showInformationMessage(`Secret "${binding}" set for ${server.name}.`);
        }
        catch (err) {
            vscode.window.showWarningMessage('Secret saved locally but backend push failed: ' +
                (err?.message || err));
        }
    }
    async testMcpServer(server) {
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `Testing MCP server "${server.name}"…` }, async () => {
            try {
                const result = await this.apiClient.refreshMcpServer(server.id);
                if (result.last_refresh_ok) {
                    const names = (result.tools ?? []).map((t) => t.name).join(', ');
                    vscode.window.showInformationMessage(`"${server.name}" OK — ${result.tools.length} tool(s): ${names}`);
                }
                else {
                    vscode.window.showErrorMessage(`"${server.name}" failed: ${result.last_refresh_error}`);
                }
            }
            catch (err) {
                vscode.window.showErrorMessage('Test failed: ' + (err?.message || err));
            }
        });
    }
    /**
     * Re-push SecretStorage-held MCP secrets into the backend's in-memory
     * cache (covers backend restarts). Called when settings load.
     */
    async syncMcpSecrets(servers) {
        for (const server of servers ?? []) {
            const secrets = {};
            for (const binding of Object.keys(server.secret_env ?? {})) {
                const value = await this.storage.getSecret(mcpSecretName(server.id, binding));
                if (value) {
                    secrets[binding] = value;
                }
            }
            if (Object.keys(secrets).length) {
                try {
                    await this.apiClient.setMcpSecrets(server.id, secrets);
                }
                catch {
                    // backend unreachable — retried on next settings load
                }
            }
        }
    }
    // ── CLI tools ────────────────────────────────────────────────────────
    /**
     * Entry point: list CLI tools + add action.
     */
    async manageCliTools() {
        let tools = [];
        try {
            tools = (await this.apiClient.listCliTools())?.tools ?? [];
        }
        catch {
            vscode.window.showErrorMessage('Agent NEO backend is unreachable.');
            return;
        }
        const items = tools.map(t => ({
            label: `$(terminal) ${t.name}`,
            description: (t.enabled ? '' : 'disabled · ') + t.executable +
                (t.available ? '' : '  (not found on PATH)'),
            detail: this.cliDetail(t),
            tool: t,
        }));
        items.push({ label: '$(add) Register CLI tool…', action: 'add' });
        const pick = await vscode.window.showQuickPick(items, {
            placeHolder: 'CLI tools — pick one to manage, or register a new one',
        });
        if (!pick) {
            return;
        }
        if (pick.action === 'add') {
            return this.addCliTool();
        }
        if (pick.tool) {
            return this.cliToolActions(pick.tool);
        }
    }
    cliDetail(t) {
        const parts = [];
        parts.push(t.available ? '✓ available' : '✗ not on PATH');
        if ((t.allowed_subcommands ?? []).length) {
            parts.push('allowlist: ' + t.allowed_subcommands.join(', '));
        }
        else {
            parts.push('all subcommands');
        }
        if ((t.default_args ?? []).length) {
            parts.push('default args: ' + t.default_args.join(' '));
        }
        return parts.join('  ·  ');
    }
    async addCliTool() {
        const name = await vscode.window.showInputBox({
            prompt: 'Tool name (e.g. gh, docker, terraform)', ignoreFocusOut: true,
        });
        if (!name) {
            return;
        }
        const executable = await vscode.window.showInputBox({
            prompt: 'Executable (name on PATH or absolute path)',
            value: name.toLowerCase(),
            ignoreFocusOut: true,
        });
        if (!executable) {
            return;
        }
        const allowlist = await vscode.window.showInputBox({
            prompt: 'Allowed subcommands (comma-separated, optional — empty allows all)',
            placeHolder: 'e.g. pr, issue, repo',
            ignoreFocusOut: true,
        });
        try {
            const tool = await this.apiClient.addCliTool({
                name,
                executable,
                allowed_subcommands: (allowlist || '').split(',').map(s => s.trim()).filter(Boolean),
            });
            vscode.window.showInformationMessage(`CLI tool "${tool.name}" registered` +
                (tool.available ? '.' : ' — warning: executable not found on PATH.'));
        }
        catch (err) {
            vscode.window.showErrorMessage('Could not register CLI tool: ' +
                (err?.response?.data?.detail || err?.message || err));
        }
    }
    async cliToolActions(tool) {
        const pick = await vscode.window.showQuickPick([
            { label: tool.enabled ? '$(circle-slash) Disable' : '$(check) Enable', action: 'toggle' },
            { label: '$(edit) Edit allowlist…', action: 'allowlist' },
            { label: '$(trash) Remove', action: 'remove' },
        ], { placeHolder: `${tool.name} — ${this.cliDetail(tool)}` });
        if (!pick) {
            return;
        }
        try {
            if (pick.action === 'toggle') {
                await this.apiClient.updateCliTool(tool.id, { enabled: !tool.enabled });
                vscode.window.showInformationMessage(`CLI tool "${tool.name}" ${tool.enabled ? 'disabled' : 'enabled'}.`);
            }
            else if (pick.action === 'allowlist') {
                const allowlist = await vscode.window.showInputBox({
                    prompt: 'Allowed subcommands (comma-separated — empty allows all)',
                    value: (tool.allowed_subcommands ?? []).join(', '),
                    ignoreFocusOut: true,
                });
                if (allowlist === undefined) {
                    return;
                }
                await this.apiClient.updateCliTool(tool.id, {
                    allowed_subcommands: allowlist.split(',').map(s => s.trim()).filter(Boolean),
                });
                vscode.window.showInformationMessage(`Allowlist updated for "${tool.name}".`);
            }
            else if (pick.action === 'remove') {
                const confirm = await vscode.window.showWarningMessage(`Remove CLI tool "${tool.name}"?`, { modal: true }, 'Remove');
                if (confirm !== 'Remove') {
                    return;
                }
                await this.apiClient.removeCliTool(tool.id);
                vscode.window.showInformationMessage(`CLI tool "${tool.name}" removed.`);
            }
        }
        catch (err) {
            vscode.window.showErrorMessage('CLI action failed: ' +
                (err?.response?.data?.detail || err?.message || err));
        }
    }
}
exports.IntegrationsManager = IntegrationsManager;
//# sourceMappingURL=integrations.js.map