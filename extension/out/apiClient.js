"use strict";
/**
 * AGENT NEO - API Client
 * Handles communication with Agent NEO backend.
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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApiClient = void 0;
const vscode = __importStar(require("vscode"));
const axios_1 = __importDefault(require("axios"));
class ApiClient {
    constructor() {
        const config = vscode.workspace.getConfiguration('agentNeo');
        this.apiUrl = config.get('apiUrl', 'http://127.0.0.1:8000');
        this.apiToken = config.get('apiToken', '');
        this.client = axios_1.default.create({
            baseURL: this.apiUrl,
            headers: {
                'Authorization': `Bearer ${this.apiToken}`,
                'Content-Type': 'application/json'
            },
            timeout: 30000
        });
    }
    /**
     * Send a chat message (with optional attachment IDs).
     */
    async sendChatMessage(message, sessionId, context, attachmentIds, model) {
        const response = await this.client.post('/chat', {
            message,
            session_id: sessionId,
            context,
            attachment_ids: attachmentIds && attachmentIds.length > 0 ? attachmentIds : undefined,
            model: model || undefined
        });
        return response.data;
    }
    /**
     * Get available/configured LLM models ({ models: string[], catalog: {id,label,provider}[] }).
     */
    async getModels() {
        const response = await this.client.get('/models');
        return response.data;
    }
    /**
     * Force a refresh of the backend model/pricing cache (provider discovery).
     */
    async refreshModels() {
        const response = await this.client.post('/models/refresh', {}, { timeout: 60000 });
        return response.data;
    }
    /**
     * Get chat history.
     */
    async getChatHistory(sessionId) {
        const response = await this.client.get('/chat/history', {
            params: { session_id: sessionId }
        });
        return response.data;
    }
    /**
     * Approve a proposed diff.
     * @param push  When true the backend commits AND pushes to remote.
     *              When false (default) it commits locally only.
     */
    async approveDiff(sessionId, approved, push = false) {
        const response = await this.client.post('/chat/approve', {
            session_id: sessionId,
            approved,
            push
        });
        return response.data;
    }
    /**
     * Delete a chat session.
     */
    async deleteSession(sessionId) {
        const response = await this.client.delete('/chat/session', {
            params: { session_id: sessionId }
        });
        return response.data;
    }
    /**
     * Get code completion.
     */
    async getCompletion(filePath, cursorLine, cursorColumn, surroundingCode, language) {
        const response = await this.client.post('/complete', {
            file_path: filePath,
            cursor_line: cursorLine,
            cursor_column: cursorColumn,
            surrounding_code: surroundingCode,
            language
        });
        return response.data;
    }
    /**
     * Upload an image or PDF attachment.
     */
    async uploadAttachment(sessionId, fileName, fileType, contentBase64) {
        const response = await this.client.post('/attachments/upload', {
            session_id: sessionId,
            file_name: fileName,
            file_type: fileType,
            content_base64: contentBase64
        });
        return response.data;
    }
    /**
     * Get contextual prompt suggestions.
     */
    async getSuggestions(currentInput, sessionId, context) {
        const response = await this.client.post('/suggestions', {
            current_input: currentInput,
            session_id: sessionId,
            context
        });
        return response.data;
    }
    /**
     * Summarise the current session and return a new session ID pre-seeded
     * with that summary.  Call this when the thread is getting too long.
     */
    async summarizeSession(sessionId) {
        const response = await this.client.post('/chat/summarize', {
            session_id: sessionId
        });
        return response.data;
    }
    /**
     * Rollback the last applied diff by running git revert locally (no push).
     */
    async rollbackLastChange(sessionId) {
        const response = await this.client.post('/chat/rollback', {
            session_id: sessionId
        });
        return response.data;
    }
    /**
     * Run a task fully autonomously (plan → diff → apply → verify).
     * @param task        Natural-language description of what to do.
     * @param sessionId   Optional existing session to continue.
     * @param context     Optional editor context (currentFile, etc.).
     * @param push        If true, push to remote after applying.
     */
    /**
     * Return the base URL + auth headers needed for fetch-based SSE streaming.
     * Callers use these to call /chat/autorun/stream via the Fetch API.
     */
    getStreamConfig() {
        return { url: this.apiUrl, token: this.apiToken };
    }
    async autoRun(task, sessionId, context, push = false, model) {
        const response = await this.client.post('/chat/autorun', {
            task,
            session_id: sessionId,
            context,
            push,
            model: model || undefined
        });
        return response.data;
    }
    // ── Managed repos ────────────────────────────────────────────────────
    /**
     * List managed repos ({ repos: [...], active_repo_id }).
     */
    async listRepos() {
        const response = await this.client.get('/repos');
        return response.data;
    }
    /**
     * Register an already-local git repo (idempotent; triggers indexing).
     */
    async attachRepo(path, name) {
        const response = await this.client.post('/repos/attach', {
            path,
            name: name || undefined
        }, { timeout: 120000 });
        return response.data;
    }
    /**
     * Clone a GitHub repo into destPath and register it. The token (if any)
     * travels only in this request body and is never persisted by the backend.
     */
    async cloneRepo(url, destPath, name, token) {
        const response = await this.client.post('/repos/clone', {
            url,
            dest_path: destPath,
            name: name || undefined,
            token: token || undefined
        }, { timeout: 300000 });
        return response.data;
    }
    /**
     * Mark a managed repo as the active one.
     */
    async activateRepo(repoId) {
        const response = await this.client.post('/repos/activate', { repo_id: repoId });
        return response.data;
    }
    /**
     * Durable run summaries recorded by the backend (newest first).
     */
    async listRuns(limit = 20) {
        const response = await this.client.get('/runs', { params: { limit } });
        return response.data;
    }
    // ── External integrations: MCP servers + CLI tools ────────────────
    /**
     * List registered MCP servers ({ servers: [...] }).
     */
    async listMcpServers() {
        const response = await this.client.get('/mcp/servers');
        return response.data;
    }
    /**
     * Register an MCP server (stdio command or remote HTTP URL).
     */
    async addMcpServer(server) {
        const response = await this.client.post('/mcp/servers', server);
        return response.data;
    }
    /**
     * Partially update an MCP server registration.
     */
    async updateMcpServer(serverId, patch) {
        const response = await this.client.patch(`/mcp/servers/${serverId}`, patch);
        return response.data;
    }
    /**
     * Remove an MCP server registration.
     */
    async removeMcpServer(serverId) {
        const response = await this.client.delete(`/mcp/servers/${serverId}`);
        return response.data;
    }
    /**
     * Discover the server's tools (tools/list) — doubles as a health check.
     */
    async refreshMcpServer(serverId) {
        const response = await this.client.post(`/mcp/servers/${serverId}/refresh`, {}, { timeout: 60000 });
        return response.data;
    }
    /**
     * Push secret values for a server's bindings. Values travel only in
     * this request body and are held in backend memory only.
     */
    async setMcpSecrets(serverId, secrets) {
        const response = await this.client.post(`/mcp/servers/${serverId}/secrets`, { secrets });
        return response.data;
    }
    /**
     * List registered CLI tools ({ tools: [...] }) with availability.
     */
    async listCliTools() {
        const response = await this.client.get('/cli/tools');
        return response.data;
    }
    /**
     * Register a governed CLI tool.
     */
    async addCliTool(tool) {
        const response = await this.client.post('/cli/tools', tool);
        return response.data;
    }
    /**
     * Partially update a CLI tool registration.
     */
    async updateCliTool(toolId, patch) {
        const response = await this.client.patch(`/cli/tools/${toolId}`, patch);
        return response.data;
    }
    /**
     * Remove a CLI tool registration.
     */
    async removeCliTool(toolId) {
        const response = await this.client.delete(`/cli/tools/${toolId}`);
        return response.data;
    }
    /**
     * Check API health.
     */
    async checkHealth() {
        try {
            const response = await this.client.get('/health');
            return response.status === 200;
        }
        catch (error) {
            return false;
        }
    }
}
exports.ApiClient = ApiClient;
//# sourceMappingURL=apiClient.js.map