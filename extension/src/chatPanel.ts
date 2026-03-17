/**
 * AGENT NEO - Chat Panel
 * Manages the chat UI panel.
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';

export class ChatPanel {
    private panel: vscode.WebviewPanel | undefined;
    private apiClient: ApiClient;
    private sessionId: string | undefined;
    private selectedModel: string = 'claude-sonnet'; // Default model

    constructor(private context: vscode.ExtensionContext) {
        this.apiClient = new ApiClient();
    }

    /**
     * Show the chat panel.
     */
    public show() {
        if (this.panel) {
            this.panel.reveal();
            return;
        }

        this.panel = vscode.window.createWebviewPanel(
            'agentNeoChat',
            'Agent NEO Chat',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        this.panel.webview.html = this.getWebviewContent();
        this.panel.onDidDispose(() => {
            this.panel = undefined;
            this.sessionId = undefined;
        });

        this.panel.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            undefined,
            this.context.subscriptions
        );
    }

    /**
     * Send a message to the chat (called from commands).
     */
    public async sendMessage(message: string, context?: any) {
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
    private async handleMessage(message: any) {
        console.log('Received message from webview:', message);

        switch (message.type) {
            case 'sendMessage':
                await this.handleSendMessage(message.message, message.context);
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
        }
    }

    /**
     * Handle sending a message to the backend.
     */
    private async handleSendMessage(message: string, context?: any) {
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

            // Send to backend
            const response = await this.apiClient.sendChatMessage(
                message,
                this.sessionId,
                context
            );

            // Update session ID
            this.sessionId = response.session_id;

            // Send response to webview
            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: response.message,
                actionType: response.action_type,
                diffProposal: response.proposed_diff
            });

        } catch (error: any) {
            console.error('Failed to send message:', error);
            this.panel?.webview.postMessage({
                type: 'error',
                message: error.message || 'Failed to send message'
            });
        } finally {
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: false
            });
        }
    }

    /**
     * Get current editor context.
     */
    private getCurrentContext(): any {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return null;
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
            workspace_path: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
            language: document.languageId
        };
    }

    /**
     * Load chat history.
     */
    private async loadHistory() {
        if (!this.sessionId) {
            return;
        }

        try {
            const history = await this.apiClient.getChatHistory(this.sessionId);
            this.panel?.webview.postMessage({
                type: 'loadHistory',
                messages: history.messages
            });
        } catch (error) {
            console.error('Failed to load history:', error);
        }
    }

    /**
     * Handle clearing the session.
     */
    private async handleClearSession() {
        if (this.sessionId) {
            try {
                await this.apiClient.deleteSession(this.sessionId);
            } catch (error) {
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
    private async handleApproveDiff(proposal: any, push: boolean = false) {
        try {
            const label = push ? 'Committing & pushing changes...' : 'Applying changes...';
            vscode.window.showInformationMessage(label);

            // Show loading state
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: true
            });

            // Call Agent NEO /chat/approve endpoint
            const response = await this.apiClient.approveDiff(this.sessionId!, true, push);

            // Show success message
            vscode.window.showInformationMessage('Changes applied successfully!');

            // Add execution result to chat
            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: response.message
            });

        } catch (error: any) {
            console.error('Failed to apply changes:', error);
            vscode.window.showErrorMessage(`Failed to apply changes: ${error.message}`);

            this.panel?.webview.postMessage({
                type: 'error',
                message: `Failed to apply changes: ${error.message}`
            });
        } finally {
            this.panel?.webview.postMessage({
                type: 'loading',
                loading: false
            });
        }
    }

    /**
     * Handle rejecting a diff proposal.
     */
    private async handleRejectDiff(proposal: any) {
        try {
            // Call Agent NEO /chat/approve endpoint with approved=false
            const response = await this.apiClient.approveDiff(this.sessionId!, false);

            this.panel?.webview.postMessage({
                type: 'assistantMessage',
                message: response.message
            });
        } catch (error: any) {
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
    private getWebviewContent(): string {
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

                    #clearBtn {
                        background: var(--vscode-button-background);
                        color: var(--vscode-button-foreground);
                        border: none;
                        padding: 4px 12px;
                        cursor: pointer;
                        font-size: 12px;
                        border-radius: 2px;
                    }

                    #clearBtn:hover {
                        background: var(--vscode-button-hoverBackground);
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
                </style>
            </head>
            <body>
                <div id="header">
                    <h1>Agent NEO Chat</h1>
                    <button id="clearBtn">Clear Session</button>
                </div>

                <div id="messages"></div>

                <div id="inputArea">
                    <textarea id="messageInput" placeholder="Ask Agent NEO anything..." rows="1"></textarea>
                    <button id="sendBtn">Send</button>
                </div>

                <script>
                    const vscode = acquireVsCodeApi();
                    const messagesDiv = document.getElementById('messages');
                    const messageInput = document.getElementById('messageInput');
                    const sendBtn = document.getElementById('sendBtn');
                    const clearBtn = document.getElementById('clearBtn');

                    let isLoading = false;

                    // Auto-resize textarea
                    messageInput.addEventListener('input', () => {
                        messageInput.style.height = 'auto';
                        messageInput.style.height = messageInput.scrollHeight + 'px';
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

                    function sendMessage() {
                        const message = messageInput.value.trim();
                        if (!message || isLoading) return;

                        // Clear input
                        messageInput.value = '';
                        messageInput.style.height = 'auto';

                        // Send to extension
                        vscode.postMessage({
                            type: 'sendMessage',
                            message: message
                        });
                    }

                    function clearSession() {
                        if (confirm('Clear chat session?')) {
                            vscode.postMessage({ type: 'clearSession' });
                        }
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

                        // Stats
                        const stats = document.createElement('div');
                        stats.className = 'diff-stats';
                        stats.textContent = `${proposal.files_changed.length} file(s) | +${proposal.additions} -${proposal.deletions}`;
                        diffDiv.appendChild(stats);

                        // Diff content
                        const diffContent = document.createElement('div');
                        diffContent.className = 'diff-content';

                        const diffLines = proposal.diff.split('\\n');
                        diffLines.forEach(line => {
                            const lineDiv = document.createElement('div');
                            lineDiv.className = 'diff-line';

                            if (line.startsWith('+') && !line.startsWith('+++')) {
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

                    // Handle messages from extension
                    window.addEventListener('message', event => {
                        const message = event.data;

                        switch (message.type) {
                            case 'userMessage':
                                addMessage('user', message.message);
                                break;

                            case 'assistantMessage':
                                addMessage('assistant', message.message, message.diffProposal);
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;

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
                                break;

                            case 'loadHistory':
                                messagesDiv.innerHTML = '';
                                message.messages.forEach(msg => {
                                    addMessage(msg.role, msg.content);
                                });
                                break;
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
     * Dispose the panel.
     */
    public dispose() {
        if (this.panel) {
            this.panel.dispose();
        }
    }
}

