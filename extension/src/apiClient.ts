/**
 * AGENT NEO - API Client
 * Handles communication with Agent NEO backend.
 */

import * as vscode from 'vscode';
import axios, { AxiosInstance } from 'axios';

export class ApiClient {
    private client: AxiosInstance;
    private apiUrl: string;
    private apiToken: string;

    constructor() {
        const config = vscode.workspace.getConfiguration('agentNeo');
        this.apiUrl = config.get('apiUrl', 'http://127.0.0.1:8000');
        this.apiToken = config.get('apiToken', '');

        this.client = axios.create({
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
    async sendChatMessage(
        message: string,
        sessionId?: string,
        context?: any,
        attachmentIds?: string[],
        model?: string
    ): Promise<any> {
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
    async getModels(): Promise<any> {
        const response = await this.client.get('/models');
        return response.data;
    }

    /**
     * Get chat history.
     */
    async getChatHistory(sessionId: string): Promise<any> {
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
    async approveDiff(sessionId: string, approved: boolean, push: boolean = false): Promise<any> {
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
    async deleteSession(sessionId: string): Promise<any> {
        const response = await this.client.delete('/chat/session', {
            params: { session_id: sessionId }
        });
        return response.data;
    }

    /**
     * Get code completion.
     */
    async getCompletion(
        filePath: string,
        cursorLine: number,
        cursorColumn: number,
        surroundingCode: string,
        language?: string
    ): Promise<any> {
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
    async uploadAttachment(
        sessionId: string,
        fileName: string,
        fileType: 'image' | 'pdf',
        contentBase64: string
    ): Promise<any> {
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
    async getSuggestions(currentInput: string, sessionId?: string, context?: any): Promise<any> {
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
    async summarizeSession(sessionId: string): Promise<any> {
        const response = await this.client.post('/chat/summarize', {
            session_id: sessionId
        });
        return response.data;
    }

    /**
     * Rollback the last applied diff by running git revert locally (no push).
     */
    async rollbackLastChange(sessionId: string): Promise<any> {
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
    getStreamConfig(): { url: string; token: string } {
        return { url: this.apiUrl, token: this.apiToken };
    }

    async autoRun(task: string, sessionId?: string, context?: any, push: boolean = false, model?: string): Promise<any> {
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
    async listRepos(): Promise<any> {
        const response = await this.client.get('/repos');
        return response.data;
    }

    /**
     * Register an already-local git repo (idempotent; triggers indexing).
     */
    async attachRepo(path: string, name?: string): Promise<any> {
        const response = await this.client.post('/repos/attach', {
            path,
            name: name || undefined
        }, { timeout: 120_000 });
        return response.data;
    }

    /**
     * Clone a GitHub repo into destPath and register it. The token (if any)
     * travels only in this request body and is never persisted by the backend.
     */
    async cloneRepo(url: string, destPath: string, name?: string, token?: string): Promise<any> {
        const response = await this.client.post('/repos/clone', {
            url,
            dest_path: destPath,
            name: name || undefined,
            token: token || undefined
        }, { timeout: 300_000 });
        return response.data;
    }

    /**
     * Mark a managed repo as the active one.
     */
    async activateRepo(repoId: string): Promise<any> {
        const response = await this.client.post('/repos/activate', { repo_id: repoId });
        return response.data;
    }

    /**
     * Durable run summaries recorded by the backend (newest first).
     */
    async listRuns(limit: number = 20): Promise<any> {
        const response = await this.client.get('/runs', { params: { limit } });
        return response.data;
    }

    /**
     * Check API health.
     */
    async checkHealth(): Promise<boolean> {
        try {
            const response = await this.client.get('/health');
            return response.status === 200;
        } catch (error) {
            return false;
        }
    }
}

