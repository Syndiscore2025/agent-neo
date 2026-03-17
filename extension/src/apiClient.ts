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
        attachmentIds?: string[]
    ): Promise<any> {
        const response = await this.client.post('/chat', {
            message,
            session_id: sessionId,
            context,
            attachment_ids: attachmentIds && attachmentIds.length > 0 ? attachmentIds : undefined
        });
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

