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
    async sendChatMessage(message, sessionId, context, attachmentIds) {
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