"use strict";
/**
 * AGENT NEO - Chat Panel
 * Manages the chat UI panel.
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
exports.ChatPanel = void 0;
const vscode = __importStar(require("vscode"));
const apiClient_1 = require("./apiClient");
class ChatPanel {
    constructor(context) {
        this.context = context;
        this.selectedModel = 'claude-sonnet'; // Default model
        this.apiClient = new apiClient_1.ApiClient();
    }
    /**
     * Show the chat panel.
     */
    show() {
        if (this.panel) {
            this.panel.reveal();
            return;
        }
        this.panel = vscode.window.createWebviewPanel('agentNeoChat', 'Agent NEO Chat', vscode.ViewColumn.Beside, {
            enableScripts: true,
            retainContextWhenHidden: true
        });
        this.panel.webview.html = this.getWebviewContent();
        this.panel.onDidDispose(() => {
            this.panel = undefined;
            this.sessionId = undefined;
        });
        this.panel.webview.onDidReceiveMessage(message => this.handleMessage(message), undefined, this.context.subscriptions);
    }
    /**
     * Send a message to the chat (called from commands).
     */
    async sendMessage(message, context) {
        if (!this.panel) {
            this.show();
        }
        // Send message to webview to display
        this.panel?.webview.postMessage({
            type: 'userMessage',
            message: message
        });
        // Send to backend
        await this.handleSendMessage(message, context);
    }
    /**
     * Handle messages from webview.
     */
    async handleMessage(message) {
        console.log('Received message from webview:', message);
        switch (message.type) {
            case 'sendMessage':
                await this.handleSendMessage(message.message, message.context, message.attachmentIds);
                break;
            case 'clearSession':
                await this.handleClearSession();
                break;
            case 'approveDiff':
                await this.handleApproveDiff(message.proposal, message.push || false);
                break;
            case 'rejectDiff':
                await this.handleRejectDiff(message.proposal);
                break;
            case 'ready':
                // Webview is ready, load history if session exists
                if (this.sessionId) {
                    await this.loadHistory();
                }
                break;
            case 'uploadAttachment':
                await this.handleUploadAttachment(message.fileName, message.fileType, message.contentBase64);
                break;
            case 'getSuggestions':
                await this.handleGetSuggestions(message.currentInput, message.context);
                break;
            case 'newThread':
                await this.handleNewThread();
                break;
            case 'rollbackChange':
                await this.handleRollback();
                break;
            case 'autoRun':
                await this.handleAutoRun(message.task);
                break;
            case 'cloneRepo':
                await this.handleCloneRepo(message.url);
                break;
        }
    }
    /**
     * Handle sending a message to the backend.
     */
    async handleSendMessage(message, context, attachmentIds) {
        try {
            // Show loading state
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: true
            });
            // Get current editor context if not provided
            if (!context) {
                context = this.getCurrentContext();
            }
            // Send to backend (with optional attachment IDs)
            const response = await this.apiClient.sendChatMessage(message, this.sessionId, context, attachmentIds);
            // Update session ID
            this.sessionId = response.session_id;
            // Send response to webview
            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: response.message,
                actionType: response.action_type,
                diffProposal: response.proposed_diff
            });
        }
        catch (error) {
            console.error('Failed to send message:', error);
            this.panel?.webview.postMessage({
                type: 'error',
                message: error.message || 'Failed to send message'
            });
        }
        finally {
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: false
            });
        }
    }
    /**
     * Get current editor context, including VS Code diagnostics (errors/warnings).
     */
    getCurrentContext() {
        const editor = vscode.window.activeTextEditor;
        const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        // Gather diagnostics from all open files (first 20 errors/warnings)
        const diagnostics = [];
        vscode.languages.getDiagnostics().forEach(([uri, diags]) => {
            diags
                .filter(d => d.severity <= vscode.DiagnosticSeverity.Warning)
                .slice(0, 5)
                .forEach(d => {
                const rel = vscode.workspace.asRelativePath(uri);
                const line = d.range.start.line + 1;
                const sev = d.severity === vscode.DiagnosticSeverity.Error ? 'ERROR' : 'WARN';
                diagnostics.push(`[${sev}] ${rel}:${line} — ${d.message}`);
            });
        });
        if (!editor) {
            return {
                workspace_path: workspacePath,
                diagnostics: diagnostics.slice(0, 20)
            };
        }
        const document = editor.document;
        const selection = editor.selection;
        const selectedText = document.getText(selection);
        return {
            current_file: vscode.workspace.asRelativePath(document.uri),
            current_file_content: selectedText ? null : document.getText(),
            selected_code: selectedText || null,
            selection_start_line: selection.start.line + 1,
            selection_end_line: selection.end.line + 1,
            workspace_path: workspacePath,
            language: document.languageId,
            diagnostics: diagnostics.slice(0, 20)
        };
    }
    /**
     * Load chat history.
     */
    async loadHistory() {
        if (!this.sessionId) {
            return;
        }
        try {
            const history = await this.apiClient.getChatHistory(this.sessionId);
            this.panel?.webview.postMessage({
                type: 'loadHistory',
                messages: history.messages
            });
        }
        catch (error) {
            console.error('Failed to load history:', error);
        }
    }
    /**
     * Handle clearing the session.
     */
    async handleClearSession() {
        if (this.sessionId) {
            try {
                await this.apiClient.deleteSession(this.sessionId);
            }
            catch (error) {
                console.error('Failed to delete session:', error);
            }
        }
        this.sessionId = undefined;
        this.panel?.webview.postMessage({
            type: 'sessionCleared'
        });
    }
    /**
     * Handle approving a diff proposal.
     * @param push  When true the backend also pushes to remote ("Commit & Push").
     */
    async handleApproveDiff(proposal, push = false) {
        try {
            const label = push ? 'Committing & pushing changes...' : 'Applying changes...';
            vscode.window.showInformationMessage(label);
            // Show loading state
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: true
            });
            // Call Agent NEO /chat/approve endpoint
            const response = await this.apiClient.approveDiff(this.sessionId, true, push);
            // Show success message
            vscode.window.showInformationMessage('Changes applied successfully!');
            // Add execution result card to chat
            this.panel?.webview.postMessage({
                type: 'executionResult',
                message: response.message,
                executionResult: response.execution_result || null
            });
        }
        catch (error) {
            console.error('Failed to apply changes:', error);
            vscode.window.showErrorMessage(`Failed to apply changes: ${error.message}`);
            this.panel?.webview.postMessage({
                type: 'error',
                message: `Failed to apply changes: ${error.message}`
            });
        }
        finally {
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: false
            });
        }
    }
    /**
     * Handle rejecting a diff proposal.
     */
    async handleRejectDiff(proposal) {
        try {
            // Call Agent NEO /chat/approve endpoint with approved=false
            const response = await this.apiClient.approveDiff(this.sessionId, false);
            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: response.message
            });
        }
        catch (error) {
            console.error('Failed to reject diff:', error);
            this.panel?.webview.postMessage({
                type: 'error',
                message: `Failed to reject diff: ${error.message}`
            });
        }
    }
    /**
     * Get webview HTML content.
     */
    getWebviewContent() {
        return `
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Agent NEO Chat</title>
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    body {
                        font-family: var(--vscode-font-family);
                        font-size: var(--vscode-font-size);
                        color: var(--vscode-foreground);
                        background-color: var(--vscode-editor-background);
                        height: 100vh;
                        display: flex;
                        flex-direction: column;
                    }

                    #header {
                        padding: 12px 16px;
                        background-color: var(--vscode-sideBar-background);
                        border-bottom: 1px solid var(--vscode-panel-border);
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }

                    #header h1 {
                        font-size: 14px;
                        font-weight: 600;
                    }

                    #headerActions {
                        display: flex;
                        gap: 6px;
                        align-items: center;
                    }

                    #clearBtn, #newThreadBtn {
                        background: var(--vscode-button-secondaryBackground, var(--vscode-button-background));
                        color: var(--vscode-button-secondaryForeground, var(--vscode-button-foreground));
                        border: none;
                        padding: 4px 10px;
                        cursor: pointer;
                        font-size: 11px;
                        border-radius: 2px;
                    }

                    #clearBtn:hover, #newThreadBtn:hover {
                        opacity: 0.85;
                    }

                    /* ── Execution result card ── */
                    .exec-result-card {
                        margin-top: 8px;
                        padding: 10px 12px;
                        background: var(--vscode-textBlockQuote-background);
                        border: 1px solid var(--vscode-textBlockQuote-border);
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    .exec-result-card .exec-title {
                        font-weight: 700;
                        margin-bottom: 6px;
                    }
                    .exec-result-card .exec-row {
                        display: flex;
                        gap: 12px;
                        flex-wrap: wrap;
                        margin-bottom: 4px;
                        opacity: 0.9;
                    }
                    .exec-result-card .exec-badge {
                        padding: 1px 7px;
                        border-radius: 8px;
                        font-size: 11px;
                        font-weight: 600;
                    }
                    .exec-badge.ok   { background: rgba(0,200,80,0.18); color: #4ec94e; }
                    .exec-badge.fail { background: rgba(255,80,80,0.18); color: #f48771; }
                    .exec-badge.sha  { background: rgba(100,100,255,0.15); color: var(--vscode-textLink-foreground); font-family: monospace; }
                    .exec-result-card .exec-steps {
                        margin-top: 6px;
                        padding-left: 16px;
                        opacity: 0.85;
                        font-size: 11px;
                    }
                    .exec-result-card .exec-actions {
                        margin-top: 8px;
                        display: flex;
                        gap: 8px;
                        flex-wrap: wrap;
                    }
                    .exec-result-card .exec-btn {
                        padding: 4px 10px;
                        border: none;
                        border-radius: 2px;
                        cursor: pointer;
                        font-size: 11px;
                    }
                    .exec-btn.undo   { background: #7a2d00; color: #fff; }
                    .exec-btn.undo:hover { opacity: 0.85; }
                    .exec-btn.copy   { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }

                    /* ── Thread-switch banner ── */
                    .thread-banner {
                        padding: 10px 14px;
                        background: rgba(100,130,255,0.12);
                        border: 1px solid rgba(100,130,255,0.4);
                        border-radius: 4px;
                        font-size: 12px;
                        align-self: stretch;
                    }
                    .thread-banner strong { display: block; margin-bottom: 4px; }

                    /* ── Slash command hint in placeholder ── */
                    #slashHint {
                        font-size: 10px;
                        opacity: 0.55;
                        padding: 0 16px 4px;
                    }

                    #messages {
                        flex: 1;
                        overflow-y: auto;
                        padding: 16px;
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                    }

                    .message {
                        display: flex;
                        flex-direction: column;
                        gap: 4px;
                        max-width: 85%;
                    }

                    .message.user {
                        align-self: flex-end;
                    }

                    .message.assistant {
                        align-self: flex-start;
                    }

                    .message-header {
                        font-size: 11px;
                        opacity: 0.7;
                        font-weight: 600;
                    }

                    .message-content {
                        padding: 8px 12px;
                        border-radius: 4px;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }

                    .message.user .message-content {
                        background-color: var(--vscode-button-background);
                        color: var(--vscode-button-foreground);
                    }

                    .message.assistant .message-content {
                        background-color: var(--vscode-input-background);
                        border: 1px solid var(--vscode-input-border);
                    }

                    .message.error .message-content {
                        background-color: var(--vscode-inputValidation-errorBackground);
                        border: 1px solid var(--vscode-inputValidation-errorBorder);
                    }

                    .diff-proposal {
                        margin-top: 8px;
                        padding: 12px;
                        background-color: var(--vscode-textBlockQuote-background);
                        border: 1px solid var(--vscode-textBlockQuote-border);
                        border-radius: 4px;
                    }

                    .diff-header {
                        font-weight: 600;
                        margin-bottom: 8px;
                        font-size: 12px;
                    }

                    .diff-stats {
                        font-size: 11px;
                        opacity: 0.8;
                        margin-bottom: 8px;
                    }

                    .diff-content {
                        background-color: var(--vscode-editor-background);
                        padding: 8px;
                        border-radius: 2px;
                        font-family: var(--vscode-editor-font-family);
                        font-size: 12px;
                        overflow-x: auto;
                        max-height: 300px;
                        overflow-y: auto;
                    }

                    .diff-line {
                        white-space: pre;
                    }

                    .diff-line.add {
                        background-color: rgba(0, 255, 0, 0.1);
                        color: #4ec9b0;
                    }

                    .diff-line.remove {
                        background-color: rgba(255, 0, 0, 0.1);
                        color: #f48771;
                    }

                    .diff-actions {
                        margin-top: 8px;
                        display: flex;
                        gap: 8px;
                    }

                    .diff-btn {
                        padding: 6px 12px;
                        border: none;
                        border-radius: 2px;
                        cursor: pointer;
                        font-size: 12px;
                    }

                    .diff-btn.approve {
                        background-color: var(--vscode-button-background);
                        color: var(--vscode-button-foreground);
                    }

                    .diff-btn.approve:hover {
                        background-color: var(--vscode-button-hoverBackground);
                    }

                    .diff-btn.reject {
                        background-color: var(--vscode-button-secondaryBackground);
                        color: var(--vscode-button-secondaryForeground);
                    }

                    .diff-btn.reject:hover {
                        background-color: var(--vscode-button-secondaryHoverBackground);
                    }

                    .diff-btn.push {
                        background-color: #0e7a0d;
                        color: #ffffff;
                    }

                    .diff-btn.push:hover {
                        background-color: #1a9e19;
                    }

                    #inputArea {
                        padding: 12px 16px;
                        background-color: var(--vscode-sideBar-background);
                        border-top: 1px solid var(--vscode-panel-border);
                        display: flex;
                        gap: 8px;
                    }

                    #messageInput {
                        flex: 1;
                        background: var(--vscode-input-background);
                        color: var(--vscode-input-foreground);
                        border: 1px solid var(--vscode-input-border);
                        padding: 8px 12px;
                        font-family: var(--vscode-font-family);
                        font-size: var(--vscode-font-size);
                        resize: none;
                        min-height: 36px;
                        max-height: 120px;
                    }

                    #messageInput:focus {
                        outline: 1px solid var(--vscode-focusBorder);
                    }

                    #sendBtn {
                        background: var(--vscode-button-background);
                        color: var(--vscode-button-foreground);
                        border: none;
                        padding: 8px 16px;
                        cursor: pointer;
                        font-size: 13px;
                        border-radius: 2px;
                        white-space: nowrap;
                    }

                    #sendBtn:hover:not(:disabled) {
                        background: var(--vscode-button-hoverBackground);
                    }

                    #sendBtn:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                    }

                    /* ── Attach + Mic buttons ── */
                    #attachBtn, #micBtn {
                        background: var(--vscode-button-secondaryBackground, var(--vscode-input-background));
                        color: var(--vscode-button-secondaryForeground, var(--vscode-foreground));
                        border: 1px solid var(--vscode-input-border);
                        padding: 8px 10px;
                        cursor: pointer;
                        font-size: 16px;
                        border-radius: 2px;
                        line-height: 1;
                    }
                    #attachBtn:hover, #micBtn:hover { opacity: 0.8; }

                    /* ── AutoRun result card ── */
                    .auto-run-card {
                        background: var(--vscode-input-background);
                        border: 1px solid var(--vscode-input-border);
                        border-radius: 6px;
                        padding: 10px 14px;
                        margin-top: 6px;
                        font-size: 12px;
                    }
                    .auto-run-header {
                        font-size: 13px;
                        margin-bottom: 8px;
                    }
                    .auto-run-steps {
                        display: flex;
                        flex-direction: column;
                        gap: 6px;
                        margin-bottom: 8px;
                    }
                    .auto-run-step {
                        padding: 4px 8px;
                        border-radius: 4px;
                        background: var(--vscode-editor-inactiveSelectionBackground);
                        line-height: 1.5;
                    }
                    .auto-run-step.step-success { border-left: 3px solid #4ec94e; }
                    .auto-run-step.step-failed  { border-left: 3px solid #e05252; }
                    .auto-run-step.step-skipped { border-left: 3px solid #888; opacity: 0.7; }
                    .step-ms { opacity: 0.55; font-size: 10px; }
                    .step-msg { opacity: 0.85; white-space: pre-wrap; }
                    .auto-run-summary {
                        font-style: italic;
                        opacity: 0.8;
                        margin-top: 4px;
                    }
                    .auto-run-commit {
                        margin-top: 4px;
                        font-family: monospace;
                        font-size: 11px;
                        opacity: 0.7;
                    }

                    /* ── Pending attachment chips (in input area) ── */
                    #attachmentPreview {
                        display: flex;
                        flex-wrap: wrap;
                        gap: 4px;
                        padding: 4px 16px 0;
                    }
                    .attachment-chip {
                        display: flex;
                        align-items: center;
                        gap: 4px;
                        background: var(--vscode-badge-background);
                        color: var(--vscode-badge-foreground);
                        border-radius: 10px;
                        padding: 2px 8px;
                        font-size: 11px;
                    }
                    .attachment-chip .remove-att {
                        cursor: pointer;
                        font-size: 13px;
                        line-height: 1;
                        opacity: 0.7;
                    }
                    .attachment-chip .remove-att:hover { opacity: 1; }

                    /* ── Suggestion chips ── */
                    #suggestionsContainer {
                        padding: 4px 16px;
                        display: flex;
                        flex-wrap: wrap;
                        gap: 6px;
                        min-height: 0;
                    }
                    .suggestion-chip {
                        background: var(--vscode-input-background);
                        color: var(--vscode-foreground);
                        border: 1px solid var(--vscode-input-border);
                        border-radius: 10px;
                        padding: 3px 10px;
                        font-size: 11px;
                        cursor: pointer;
                        transition: background 0.15s;
                    }
                    .suggestion-chip:hover {
                        background: var(--vscode-list-hoverBackground);
                        border-color: var(--vscode-focusBorder);
                    }

                    /* ── Diff improvements (SLICE 9) ── */
                    .diff-file-label {
                        font-size: 11px;
                        font-family: var(--vscode-editor-font-family);
                        opacity: 0.8;
                        margin-bottom: 4px;
                        padding: 2px 4px;
                        background: var(--vscode-editor-background);
                        border-radius: 2px;
                    }
                    .diff-line.hunk {
                        color: var(--vscode-textLink-foreground);
                        background: transparent;
                        font-style: italic;
                    }
                    .diff-btn.push {
                        background: var(--vscode-button-secondaryBackground, #2d5fa8);
                        color: var(--vscode-button-secondaryForeground, #ffffff);
                    }
                    .diff-btn.push:hover { opacity: 0.85; }
                </style>
            </head>
            <body>
                <div id="header">
                    <h1>Agent NEO Chat</h1>
                    <div id="headerActions">
                        <button id="newThreadBtn" title="Summarise this thread and start fresh">🔄 New Thread</button>
                        <button id="clearBtn">Clear Session</button>
                    </div>
                </div>

                <div id="messages"></div>

                <div id="suggestionsContainer"></div>
                <div id="attachmentPreview"></div>
                <div id="slashHint">💡 Slash commands: /plan &nbsp;/fix &nbsp;/verify &nbsp;/rollback &nbsp;/run &lt;task&gt; &nbsp;/clone &lt;url&gt; &nbsp;/help</div>

                <div id="inputArea">
                    <button id="attachBtn" title="Attach image or PDF">📎</button>
                    <input type="file" id="fileInput" accept="image/*,.pdf" style="display:none">
                    <button id="micBtn" title="Speak your message (Speech-to-Text)">🎤</button>
                    <textarea id="messageInput" placeholder="Ask Agent NEO anything... (or use /commands)" rows="1"></textarea>
                    <button id="sendBtn">Send</button>
                </div>

                <script>
                    const vscode = acquireVsCodeApi();
                    const messagesDiv = document.getElementById('messages');
                    const messageInput = document.getElementById('messageInput');
                    const sendBtn = document.getElementById('sendBtn');
                    const clearBtn = document.getElementById('clearBtn');
                    const newThreadBtn = document.getElementById('newThreadBtn');
                    const attachBtn = document.getElementById('attachBtn');
                    const fileInput = document.getElementById('fileInput');
                    const micBtn = document.getElementById('micBtn');
                    const suggestionsContainer = document.getElementById('suggestionsContainer');
                    const attachmentPreview = document.getElementById('attachmentPreview');

                    let isLoading = false;
                    let messageCount = 0;           // track thread length
                    const NEW_THREAD_THRESHOLD = 20; // suggest new thread after N messages
                    // SLICE 6 — pending attachments accumulate until message is sent
                    let pendingAttachmentIds = [];
                    // SLICE 8 — typing debounce timer
                    let suggestionTimer = null;

                    // ── Auto-resize textarea ──
                    messageInput.addEventListener('input', () => {
                        messageInput.style.height = 'auto';
                        messageInput.style.height = messageInput.scrollHeight + 'px';
                        // SLICE 8 — debounced suggestion fetch (600 ms after last keystroke)
                        clearTimeout(suggestionTimer);
                        const val = messageInput.value.trim();
                        if (val.length >= 2) {
                            suggestionTimer = setTimeout(() => fetchSuggestions(val), 600);
                        } else {
                            clearSuggestions();
                        }
                    });

                    // Send message on Enter (Shift+Enter for new line)
                    messageInput.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            sendMessage();
                        }
                    });

                    sendBtn.addEventListener('click', sendMessage);
                    clearBtn.addEventListener('click', clearSession);
                    newThreadBtn.addEventListener('click', () => {
                        vscode.postMessage({ type: 'newThread' });
                    });

                    // ── SLICE 6 — attach button ──
                    attachBtn.addEventListener('click', () => fileInput.click());

                    fileInput.addEventListener('change', () => {
                        const file = fileInput.files && fileInput.files[0];
                        if (!file) return;
                        fileInput.value = ''; // reset so same file can be re-selected

                        const isPdf = file.type === 'application/pdf' || file.name.endsWith('.pdf');
                        const fileType = isPdf ? 'pdf' : 'image';

                        const reader = new FileReader();
                        reader.onload = (ev) => {
                            // Strip data-URL prefix: "data:<mime>;base64,"
                            const dataUrl = ev.target.result;
                            const base64 = dataUrl.split(',')[1];
                            vscode.postMessage({
                                type: 'uploadAttachment',
                                fileName: file.name,
                                fileType: fileType,
                                contentBase64: base64
                            });
                        };
                        reader.readAsDataURL(file);
                    });

                    // ── Speech-to-Text via Web Speech API ──────────────────────────────
                    let sttRecognition = null;
                    let sttActive = false;
                    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                        const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
                        sttRecognition = new SpeechRecognitionCtor();
                        sttRecognition.continuous = false;
                        sttRecognition.interimResults = true;
                        sttRecognition.lang = 'en-US';

                        sttRecognition.onstart = () => {
                            sttActive = true;
                            micBtn.textContent = '🔴';
                            micBtn.title = 'Recording… click to stop';
                        };
                        sttRecognition.onresult = (event) => {
                            let transcript = '';
                            for (let i = event.resultIndex; i < event.results.length; i++) {
                                transcript += event.results[i][0].transcript;
                            }
                            messageInput.value = transcript;
                            messageInput.style.height = 'auto';
                            messageInput.style.height = messageInput.scrollHeight + 'px';
                        };
                        sttRecognition.onend = () => {
                            sttActive = false;
                            micBtn.textContent = '🎤';
                            micBtn.title = 'Speak your message (Speech-to-Text)';
                        };
                        sttRecognition.onerror = (event) => {
                            console.error('STT error', event.error);
                            sttActive = false;
                            micBtn.textContent = '🎤';
                        };

                        micBtn.addEventListener('click', () => {
                            if (sttActive) {
                                sttRecognition.stop();
                            } else {
                                messageInput.value = '';
                                sttRecognition.start();
                            }
                        });
                    } else {
                        // Browser doesn't support STT — hide the button
                        micBtn.style.display = 'none';
                    }

                    // Slash command dispatch — runs BEFORE sending to backend
                    function handleSlashCommand(cmd) {
                        const lower = cmd.toLowerCase().trim();
                        if (lower === '/rollback' || lower === '/undo') {
                            vscode.postMessage({ type: 'rollbackChange' });
                            return true;
                        }
                        if (lower === '/newthread' || lower === '/new') {
                            vscode.postMessage({ type: 'newThread' });
                            return true;
                        }
                        if (lower === '/help') {
                            addMessage('assistant',
                                'Available slash commands:\\n' +
                                '/plan    — ask Agent NEO to plan changes before applying\\n' +
                                '/fix     — attempt to auto-fix failing tests\\n' +
                                '/verify  — re-run tests and report status\\n' +
                                '/rollback or /undo — revert last applied commit (local only)\\n' +
                                '/newthread or /new  — summarise thread and continue in fresh session\\n' +
                                '/run <task>         — run a task fully autonomously (no mid-step approvals)\\n' +
                                '/clone <github-url> — clone a GitHub repo and open it in VS Code'
                            );
                            return true;
                        }
                        // /run <task> → autonomous task runner
                        if (lower.startsWith('/run ')) {
                            const task = cmd.slice(5).trim();
                            if (task) {
                                vscode.postMessage({ type: 'autoRun', task });
                                return true;
                            }
                        }
                        // /clone <url> → clone GitHub repo and open folder
                        if (lower.startsWith('/clone ')) {
                            const url = cmd.slice(7).trim();
                            if (url) {
                                vscode.postMessage({ type: 'cloneRepo', url });
                                return true;
                            }
                        }
                        // /plan, /fix, /verify → pass through to LLM with added intent hint
                        if (['/plan', '/fix', '/verify'].includes(lower)) {
                            return false; // let LLM handle it
                        }
                        return false;
                    }

                    function sendMessage() {
                        const message = messageInput.value.trim();
                        if (!message || isLoading) return;

                        // Clear input and suggestions
                        messageInput.value = '';
                        messageInput.style.height = 'auto';
                        clearSuggestions();

                        // Intercept slash commands before sending to backend
                        if (message.startsWith('/')) {
                            const handled = handleSlashCommand(message);
                            if (handled) return;
                            // Unrecognised slash command — pass through so LLM can respond
                        }

                        // Capture and reset pending attachments
                        const attachmentIds = [...pendingAttachmentIds];
                        pendingAttachmentIds = [];
                        attachmentPreview.innerHTML = '';

                        messageCount++;

                        // Nudge toward new thread when threshold is hit
                        if (messageCount === NEW_THREAD_THRESHOLD) {
                            addMessage('assistant',
                                '💡 This thread is getting long (' + messageCount + ' messages). ' +
                                'Click **🔄 New Thread** in the header to summarise and continue fresh, ' +
                                'or keep going here.'
                            );
                        }

                        // Send to extension
                        vscode.postMessage({
                            type: 'sendMessage',
                            message: message,
                            attachmentIds: attachmentIds.length > 0 ? attachmentIds : undefined
                        });
                    }

                    function clearSession() {
                        if (confirm('Clear chat session?')) {
                            pendingAttachmentIds = [];
                            attachmentPreview.innerHTML = '';
                            clearSuggestions();
                            vscode.postMessage({ type: 'clearSession' });
                        }
                    }

                    // ── SLICE 8 — Suggestions ──
                    function fetchSuggestions(input) {
                        vscode.postMessage({ type: 'getSuggestions', currentInput: input });
                    }

                    function clearSuggestions() {
                        suggestionsContainer.innerHTML = '';
                    }

                    function renderSuggestions(suggestions) {
                        suggestionsContainer.innerHTML = '';
                        suggestions.forEach(text => {
                            const chip = document.createElement('button');
                            chip.className = 'suggestion-chip';
                            chip.textContent = text;
                            chip.onclick = () => {
                                messageInput.value = text;
                                messageInput.dispatchEvent(new Event('input'));
                                clearSuggestions();
                                messageInput.focus();
                            };
                            suggestionsContainer.appendChild(chip);
                        });
                    }

                    // ── SLICE 6 — Attachment preview in input bar ──
                    function addAttachmentChip(attachmentId, fileName) {
                        pendingAttachmentIds.push(attachmentId);
                        const chip = document.createElement('div');
                        chip.className = 'attachment-chip';
                        chip.dataset.id = attachmentId;
                        chip.innerHTML =
                            '<span>📎 ' + fileName + '</span>' +
                            '<span class="remove-att" title="Remove">×</span>';
                        chip.querySelector('.remove-att').onclick = () => {
                            pendingAttachmentIds = pendingAttachmentIds.filter(id => id !== attachmentId);
                            chip.remove();
                        };
                        attachmentPreview.appendChild(chip);
                    }

                    // ── Execution result card renderer ──────────────────────────────
                    function createExecResultCard(result) {
                        const card = document.createElement('div');
                        card.className = 'exec-result-card';

                        const title = document.createElement('div');
                        title.className = 'exec-title';
                        const icon = result.status === 'Working' ? '✅' : '❌';
                        title.textContent = icon + ' Execution Result';
                        card.appendChild(title);

                        // Badge row
                        const row = document.createElement('div');
                        row.className = 'exec-row';

                        function badge(text, cls) {
                            const b = document.createElement('span');
                            b.className = 'exec-badge ' + cls;
                            b.textContent = text;
                            return b;
                        }

                        row.appendChild(badge(result.status || '—', result.status === 'Working' ? 'ok' : 'fail'));
                        row.appendChild(badge(result.mode || 'CRITICAL', 'ok'));
                        if (result.commit_sha) {
                            row.appendChild(badge(result.commit_sha.slice(0, 8), 'sha'));
                        }
                        if (result.pushed) {
                            row.appendChild(badge('Pushed ✓', 'ok'));
                        }
                        if (result.pre_test_passed !== null && result.pre_test_passed !== undefined) {
                            row.appendChild(badge('Pre-tests: ' + (result.pre_test_passed ? '✓' : '✗'), result.pre_test_passed ? 'ok' : 'fail'));
                        }
                        if (result.post_test_passed !== null && result.post_test_passed !== undefined) {
                            row.appendChild(badge('Post-tests: ' + (result.post_test_passed ? '✓' : '✗'), result.post_test_passed ? 'ok' : 'fail'));
                        }
                        card.appendChild(row);

                        // Files changed
                        if (result.files_changed && result.files_changed.length > 0) {
                            const files = document.createElement('div');
                            files.style.fontSize = '11px';
                            files.style.opacity = '0.8';
                            files.style.marginTop = '4px';
                            files.textContent = 'Files: ' + result.files_changed.join(', ');
                            card.appendChild(files);
                        }

                        // Verify steps
                        if (result.verify_steps && result.verify_steps.length > 0) {
                            const steps = document.createElement('ul');
                            steps.className = 'exec-steps';
                            result.verify_steps.forEach(s => {
                                const li = document.createElement('li');
                                li.textContent = s;
                                steps.appendChild(li);
                            });
                            card.appendChild(steps);
                        }

                        // Error
                        if (result.error) {
                            const err = document.createElement('div');
                            err.style.color = 'var(--vscode-errorForeground)';
                            err.style.marginTop = '4px';
                            err.style.fontSize = '11px';
                            err.textContent = '⚠️ ' + result.error;
                            card.appendChild(err);
                        }

                        // Action buttons
                        const actions = document.createElement('div');
                        actions.className = 'exec-actions';

                        if (result.commit_sha) {
                            const undoBtn = document.createElement('button');
                            undoBtn.className = 'exec-btn undo';
                            undoBtn.textContent = '↩ Undo Last Change';
                            undoBtn.title = 'Run git revert locally (no push)';
                            undoBtn.onclick = () => vscode.postMessage({ type: 'rollbackChange' });
                            actions.appendChild(undoBtn);
                        }

                        if (result.rollback_command) {
                            const copyBtn = document.createElement('button');
                            copyBtn.className = 'exec-btn copy';
                            copyBtn.textContent = '📋 Copy Rollback Cmd';
                            copyBtn.onclick = () => navigator.clipboard.writeText(result.rollback_command);
                            actions.appendChild(copyBtn);
                        }

                        card.appendChild(actions);
                        return card;
                    }

                    function addMessage(role, content, diffProposal = null) {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = 'message ' + role;

                        const headerDiv = document.createElement('div');
                        headerDiv.className = 'message-header';
                        headerDiv.textContent = role === 'user' ? 'You' : 'Agent NEO';

                        const contentDiv = document.createElement('div');
                        contentDiv.className = 'message-content';
                        contentDiv.textContent = content;

                        messageDiv.appendChild(headerDiv);
                        messageDiv.appendChild(contentDiv);

                        // Add diff proposal if present
                        if (diffProposal) {
                            const diffDiv = createDiffProposal(diffProposal);
                            messageDiv.appendChild(diffDiv);
                        }

                        messagesDiv.appendChild(messageDiv);
                        scrollToBottom();
                    }

                    function createDiffProposal(proposal) {
                        const diffDiv = document.createElement('div');
                        diffDiv.className = 'diff-proposal';

                        // Header
                        const header = document.createElement('div');
                        header.className = 'diff-header';
                        header.textContent = '📝 Proposed Changes';
                        diffDiv.appendChild(header);

                        // Stats + file list (SLICE 9 improvement)
                        const stats = document.createElement('div');
                        stats.className = 'diff-stats';
                        const fileList = (proposal.files_changed || []).join(', ') || 'unknown';
                        stats.textContent =
                            proposal.files_changed.length + ' file(s) changed  |  ' +
                            '+' + proposal.additions + '  -' + proposal.deletions + '  |  ' +
                            fileList;
                        diffDiv.appendChild(stats);

                        // Diff content — with hunk-header styling (SLICE 9)
                        const diffContent = document.createElement('div');
                        diffContent.className = 'diff-content';

                        const diffLines = proposal.diff.split('\\n');
                        diffLines.forEach(line => {
                            const lineDiv = document.createElement('div');
                            lineDiv.className = 'diff-line';

                            if (line.startsWith('@@')) {
                                lineDiv.classList.add('hunk');
                            } else if (line.startsWith('+') && !line.startsWith('+++')) {
                                lineDiv.classList.add('add');
                            } else if (line.startsWith('-') && !line.startsWith('---')) {
                                lineDiv.classList.add('remove');
                            }

                            lineDiv.textContent = line;
                            diffContent.appendChild(lineDiv);
                        });

                        diffDiv.appendChild(diffContent);

                        // Actions
                        const actions = document.createElement('div');
                        actions.className = 'diff-actions';

                        const approveBtn = document.createElement('button');
                        approveBtn.className = 'diff-btn approve';
                        approveBtn.textContent = '✓ Apply Changes';
                        approveBtn.title = 'Commit changes locally (no push)';
                        approveBtn.onclick = () => approveDiff(proposal, false);

                        const pushBtn = document.createElement('button');
                        pushBtn.className = 'diff-btn push';
                        pushBtn.textContent = '🚀 Commit & Push';
                        pushBtn.title = 'Commit changes locally AND push to remote';
                        pushBtn.onclick = () => approveDiff(proposal, true);

                        const rejectBtn = document.createElement('button');
                        rejectBtn.className = 'diff-btn reject';
                        rejectBtn.textContent = '✗ Reject';
                        rejectBtn.onclick = () => rejectDiff(proposal);

                        actions.appendChild(approveBtn);
                        actions.appendChild(pushBtn);
                        actions.appendChild(rejectBtn);
                        diffDiv.appendChild(actions);

                        return diffDiv;
                    }

                    function approveDiff(proposal, push) {
                        vscode.postMessage({
                            type: 'approveDiff',
                            proposal: proposal,
                            push: push
                        });
                    }

                    function rejectDiff(proposal) {
                        vscode.postMessage({
                            type: 'rejectDiff',
                            proposal: proposal
                        });
                    }

                    function scrollToBottom() {
                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                    }

                    function escapeHtml(str) {
                        if (!str) { return ''; }
                        return String(str)
                            .replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replace(/"/g, '&quot;');
                    }

                    // Handle messages from extension
                    window.addEventListener('message', event => {
                        const message = event.data;

                        switch (message.type) {
                            case 'userMessage':
                                addMessage('user', message.message);
                                messageCount++;
                                break;

                            case 'assistantMessage':
                                addMessage('assistant', message.message, message.diffProposal);
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;

                            // Wave 2: typed execution result card
                            case 'executionResult': {
                                const msgDiv = document.createElement('div');
                                msgDiv.className = 'message assistant';
                                const hdr = document.createElement('div');
                                hdr.className = 'message-header';
                                hdr.textContent = 'Agent NEO';
                                const txt = document.createElement('div');
                                txt.className = 'message-content';
                                txt.textContent = message.message || '✓ Done';
                                msgDiv.appendChild(hdr);
                                msgDiv.appendChild(txt);
                                if (message.executionResult) {
                                    msgDiv.appendChild(createExecResultCard(message.executionResult));
                                }
                                messagesDiv.appendChild(msgDiv);
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;
                            }

                            // Wave 2: thread switched
                            case 'threadSwitched': {
                                messagesDiv.innerHTML = '';
                                messageCount = 0;
                                const banner = document.createElement('div');
                                banner.className = 'thread-banner';
                                banner.innerHTML =
                                    '<strong>🔄 New thread started</strong>' +
                                    'Previous conversation (' + message.messageCountWas + ' messages) has been summarised:<br><br>' +
                                    '<em>' + (message.summary || '').slice(0, 400) + '</em>';
                                messagesDiv.appendChild(banner);
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                                break;
                            }

                            case 'error':
                                addMessage('error', 'Error: ' + message.message);
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;

                            case 'loading':
                                isLoading = message.loading;
                                sendBtn.disabled = message.loading;
                                break;

                            case 'sessionCleared':
                                messagesDiv.innerHTML = '';
                                messageCount = 0;
                                break;

                            case 'loadHistory':
                                messagesDiv.innerHTML = '';
                                messageCount = 0;
                                message.messages.forEach(msg => {
                                    addMessage(msg.role, msg.content);
                                    messageCount++;
                                });
                                break;

                            // SLICE 6 — attachment responses
                            case 'attachmentUploaded':
                                addAttachmentChip(message.attachmentId, message.fileName);
                                break;

                            case 'attachmentError':
                                addMessage('error', '⚠️ Attachment: ' + message.message);
                                break;

                            // SLICE 8 — suggestion chips
                            case 'suggestions':
                                renderSuggestions(message.suggestions || []);
                                break;

                            // ── Legacy batch autorun result (kept for fallback) ──
                            case 'autoRunResult': {
                                const iconMap = { success: '✅', failed: '❌', skipped: '⏭️' };
                                const statusIcon = message.overallStatus === 'success' ? '✅' : '❌';
                                let html = '<div class="auto-run-card">';
                                html += '<div class="auto-run-header">';
                                html += statusIcon + ' <strong>AutoRun:</strong> ' + escapeHtml(message.task);
                                html += '</div><div class="auto-run-steps">';
                                (message.steps || []).forEach(step => {
                                    const icon = iconMap[step.status] || '⬜';
                                    const ms = step.duration_ms ? ' <span class="step-ms">(' + step.duration_ms + 'ms)</span>' : '';
                                    html += '<div class="auto-run-step step-' + step.status + '">';
                                    html += icon + ' <strong>' + step.step_name.toUpperCase() + '</strong>' + ms + '<br>';
                                    html += '<span class="step-msg">' + escapeHtml(step.message) + '</span></div>';
                                });
                                html += '</div><div class="auto-run-summary">' + escapeHtml(message.summary) + '</div>';
                                if (message.executionResult && message.executionResult.commit_sha) {
                                    html += '<div class="auto-run-commit">🔖 Commit: ' + message.executionResult.commit_sha.slice(0, 8) + '</div>';
                                }
                                html += '</div>';
                                const wrapper = document.createElement('div');
                                wrapper.className = 'message assistant';
                                wrapper.innerHTML = html;
                                messagesDiv.appendChild(wrapper);
                                scrollToBottom();
                                break;
                            }

                            // ── Live streaming run card ──────────────────────────
                            case 'streamRunStart': {
                                // Create a live card element we'll update in-place
                                const card = document.createElement('div');
                                card.className = 'message assistant';
                                card.id = 'streamRunCard';
                                card.innerHTML =
                                    '<div class="auto-run-card">' +
                                    '<div class="auto-run-header" id="srHeader">⚙️ <strong>Running:</strong> ' + escapeHtml(message.task) + '</div>' +
                                    '<div class="auto-run-steps" id="srSteps"></div>' +
                                    '<div id="srTokens" style="font-style:italic;opacity:0.75;font-size:12px;padding-top:4px;white-space:pre-wrap"></div>' +
                                    '</div>';
                                messagesDiv.appendChild(card);
                                scrollToBottom();
                                break;
                            }

                            case 'streamEvent': {
                                const ev = message.event || {};
                                const stepsEl = document.getElementById('srSteps');
                                const tokensEl = document.getElementById('srTokens');
                                const headerEl = document.getElementById('srHeader');

                                if (ev.type === 'text' && tokensEl) {
                                    tokensEl.textContent += ev.content || '';
                                    scrollToBottom();
                                } else if (ev.type === 'tool_start' && stepsEl) {
                                    const row = document.createElement('div');
                                    row.className = 'auto-run-step';
                                    row.id = 'sr_tool_' + (ev.tool || 'unknown');
                                    row.innerHTML = '🔧 <strong>' + escapeHtml(ev.tool || '') + '</strong> <span style="opacity:.6">running…</span>';
                                    stepsEl.appendChild(row);
                                    scrollToBottom();
                                } else if (ev.type === 'tool_end' && stepsEl) {
                                    const existing = document.getElementById('sr_tool_' + ev.tool);
                                    const ms = ev.duration_ms ? ' (' + ev.duration_ms + 'ms)' : '';
                                    const snippet = (ev.result || '').slice(0, 120);
                                    const row = existing || document.createElement('div');
                                    row.className = 'auto-run-step step-success';
                                    row.innerHTML = '✅ <strong>' + escapeHtml(ev.tool || '') + '</strong>' + ms +
                                        (snippet ? '<br><span class="step-msg">' + escapeHtml(snippet) + '</span>' : '');
                                    if (!existing) { stepsEl.appendChild(row); }
                                    scrollToBottom();
                                } else if (ev.type === 'finish') {
                                    if (headerEl) {
                                        headerEl.innerHTML = (ev.success ? '✅' : '❌') + ' <strong>AutoRun done</strong>';
                                    }
                                    if (tokensEl && ev.summary) {
                                        tokensEl.textContent = ev.summary;
                                    }
                                    scrollToBottom();
                                } else if (ev.type === 'commit') {
                                    const card = document.getElementById('streamRunCard');
                                    if (card) {
                                        const c = document.createElement('div');
                                        c.className = 'auto-run-commit';
                                        c.textContent = '🔖 Committed: ' + (ev.sha || '').slice(0, 8);
                                        card.querySelector('.auto-run-card')?.appendChild(c);
                                    }
                                } else if (ev.type === 'error') {
                                    if (headerEl) {
                                        headerEl.innerHTML = '❌ <strong>Error:</strong> ' + escapeHtml(ev.error || 'Unknown error');
                                    }
                                }
                                break;
                            }

                            case 'streamRunDone': {
                                // Remove the live card ID so future events don't affect it
                                const card = document.getElementById('streamRunCard');
                                if (card) { card.removeAttribute('id'); }
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;
                            }
                        }
                    });

                    // Notify extension that webview is ready
                    vscode.postMessage({ type: 'ready' });
                </script>
            </body>
            </html>
        `;
    }
    /**
     * Handle "Continue in New Thread" — summarise + switch session.
     */
    async handleNewThread() {
        if (!this.sessionId) {
            return;
        }
        try {
            this.panel?.webview.postMessage({ type: 'loading', loading: true });
            const result = await this.apiClient.summarizeSession(this.sessionId);
            // Switch the active session
            const oldId = this.sessionId;
            this.sessionId = result.new_session_id;
            vscode.window.showInformationMessage(`New thread started (${result.message_count_was} messages summarised).`);
            this.panel?.webview.postMessage({
                type: 'threadSwitched',
                newSessionId: result.new_session_id,
                summary: result.summary,
                messageCountWas: result.message_count_was,
                oldSessionId: oldId,
            });
        }
        catch (error) {
            vscode.window.showErrorMessage(`Failed to start new thread: ${error.message}`);
            this.panel?.webview.postMessage({
                type: 'error',
                message: `Failed to start new thread: ${error.message}`
            });
        }
        finally {
            this.panel?.webview.postMessage({ type: 'loading', loading: false });
        }
    }
    /**
     * Handle "Undo Last Change" rollback request.
     */
    async handleRollback() {
        if (!this.sessionId) {
            return;
        }
        const confirm = await vscode.window.showWarningMessage('This will run git revert on the last applied commit (local only, no push). Continue?', 'Yes, roll back', 'Cancel');
        if (confirm !== 'Yes, roll back') {
            return;
        }
        try {
            this.panel?.webview.postMessage({ type: 'loading', loading: true });
            const result = await this.apiClient.rollbackLastChange(this.sessionId);
            const icon = result.success ? '✓' : '✗';
            vscode.window.showInformationMessage(`${icon} ${result.message}`);
            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: `${icon} **Rollback**: ${result.message}`
            });
        }
        catch (error) {
            vscode.window.showErrorMessage(`Rollback failed: ${error.message}`);
            this.panel?.webview.postMessage({
                type: 'error',
                message: `Rollback failed: ${error.message}`
            });
        }
        finally {
            this.panel?.webview.postMessage({ type: 'loading', loading: false });
        }
    }
    /**
     * Handle file attachment upload from webview.
     */
    async handleUploadAttachment(fileName, fileType, contentBase64) {
        try {
            if (!this.sessionId) {
                // Create a temporary session ID; will be replaced on first chat send
                this.sessionId = `tmp-${Date.now()}`;
            }
            const result = await this.apiClient.uploadAttachment(this.sessionId, fileName, fileType, contentBase64);
            this.panel?.webview.postMessage({
                type: 'attachmentUploaded',
                attachmentId: result.attachment_id,
                fileName: result.file_name,
                fileType: result.file_type
            });
        }
        catch (error) {
            console.error('Attachment upload failed:', error);
            this.panel?.webview.postMessage({
                type: 'attachmentError',
                message: `Upload failed: ${error.message}`
            });
        }
    }
    /**
     * Handle suggestions request from webview.
     */
    async handleGetSuggestions(currentInput, context) {
        try {
            const config = vscode.workspace.getConfiguration('agentNeo');
            if (!config.get('enableSuggestions', true)) {
                return;
            }
            const result = await this.apiClient.getSuggestions(currentInput, this.sessionId, context);
            this.panel?.webview.postMessage({
                type: 'suggestions',
                suggestions: result.suggestions || []
            });
        }
        catch (error) {
            // Suggestions are non-critical — silently ignore failures
            console.debug('Suggestions request failed:', error.message);
        }
    }
    /**
     * Handle autonomous task run request from webview using SSE streaming.
     * Each event is forwarded to the webview as it arrives so step cards
     * update in real-time instead of waiting for the full loop to finish.
     */
    async handleAutoRun(task) {
        if (!task) {
            return;
        }
        // Show the user's /run message immediately
        this.panel?.webview.postMessage({ type: 'userMessage', message: `/run ${task}` });
        // Open a live streaming card in the webview
        this.panel?.webview.postMessage({ type: 'streamRunStart', task });
        const context = this.getCurrentContext();
        const { url, token } = this.apiClient.getStreamConfig();
        const body = JSON.stringify({
            task,
            session_id: this.sessionId,
            context,
        });
        try {
            const response = await fetch(`${url}/chat/autorun/stream`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body,
            });
            if (!response.ok || !response.body) {
                throw new Error(`SSE connect failed: ${response.status}`);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                buf += decoder.decode(value, { stream: true });
                // SSE lines are separated by \n\n
                const parts = buf.split('\n\n');
                buf = parts.pop() ?? ''; // keep incomplete tail
                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith('data:')) {
                        continue;
                    }
                    const json = line.slice(5).trim();
                    if (!json || json === '[DONE]') {
                        continue;
                    }
                    try {
                        const event = JSON.parse(json);
                        // Forward every SSE event directly to the webview
                        this.panel?.webview.postMessage({ type: 'streamEvent', event });
                        // File reveal: open written files in the VS Code editor
                        if (event.type === 'tool_end' && event.tool === 'write_file' && event.path) {
                            this._revealFile(event.path);
                        }
                    }
                    catch {
                        // malformed chunk — skip
                    }
                }
            }
        }
        catch (error) {
            console.error('AutoRun stream failed:', error);
            this.panel?.webview.postMessage({
                type: 'streamEvent',
                event: { type: 'error', error: error.message }
            });
        }
        finally {
            this.panel?.webview.postMessage({ type: 'streamRunDone' });
        }
    }
    /**
     * Open a file written by the agent in the VS Code editor.
     * path is repo-relative; resolved against the current workspace root.
     */
    async _revealFile(relPath) {
        try {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders || workspaceFolders.length === 0) {
                return;
            }
            const root = workspaceFolders[0].uri;
            const fileUri = vscode.Uri.joinPath(root, relPath);
            const doc = await vscode.workspace.openTextDocument(fileUri);
            await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: true });
        }
        catch {
            // file might not be in the current workspace — silently skip
        }
    }
    /**
     * Clone a GitHub repo to a user-chosen folder, then open it in VS Code.
     */
    async handleCloneRepo(url) {
        if (!url) {
            vscode.window.showWarningMessage('Usage: /clone <github-url>');
            return;
        }
        const picks = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Clone into this folder',
        });
        if (!picks || picks.length === 0) {
            return;
        }
        const destDir = picks[0].fsPath;
        const repoName = url.split('/').pop()?.replace(/\.git$/, '') || 'repo';
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const path = require('path');
        const clonePath = path.join(destDir, repoName);
        this.panel?.webview.postMessage({ type: 'userMessage', message: `/clone ${url}` });
        this.panel?.webview.postMessage({ type: 'loading', loading: true });
        const clonePromise = new Promise((resolve, reject) => {
            // eslint-disable-next-line @typescript-eslint/no-var-requires
            const cp = require('child_process');
            cp.execFile('git', ['clone', url, clonePath], { timeout: 120000 }, (err) => {
                if (err) {
                    reject(err);
                }
                else {
                    resolve();
                }
            });
        });
        vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `Cloning ${repoName}…`, cancellable: false }, () => clonePromise);
        clonePromise.then(async () => {
            const folderUri = vscode.Uri.file(clonePath);
            // Open the cloned folder in the current window so the backend
            // picks up the new workspace_path on the next /run.
            await vscode.commands.executeCommand('vscode.openFolder', folderUri, { forceNewWindow: false });
        }).catch((err) => {
            vscode.window.showErrorMessage(`Clone failed: ${err.message}`);
            this.panel?.webview.postMessage({ type: 'error', message: `Clone failed: ${err.message}` });
        }).finally(() => {
            this.panel?.webview.postMessage({ type: 'loading', loading: false });
        });
    }
    /**
     * Dispose the panel.
     */
    dispose() {
        if (this.panel) {
            this.panel.dispose();
        }
    }
}
exports.ChatPanel = ChatPanel;
//# sourceMappingURL=chatPanel.js.map