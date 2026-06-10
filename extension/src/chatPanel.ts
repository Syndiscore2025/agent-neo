/**
 * AGENT NEO - Chat Panel
 * Manages the chat UI panel.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { ApiClient } from './apiClient';
import { NeoStorage } from './storage';
import { IntegrationsManager } from './integrations';

export class ChatPanel implements vscode.WebviewViewProvider {
    public static readonly viewId = 'agent-neo.chatView';

    private panel: vscode.WebviewPanel | undefined;
    private view: vscode.WebviewView | undefined;
    private terminal: vscode.Terminal | undefined;
    private gitRepo: any;
    private workspaceInfoTimer: ReturnType<typeof setTimeout> | undefined;
    private apiClient: ApiClient;
    private storage: NeoStorage;
    private integrations: IntegrationsManager;
    private sessionId: string | undefined;
    private selectedModel: string = ''; // empty → backend DEFAULT_MODEL

    constructor(private context: vscode.ExtensionContext) {
        this.apiClient = new ApiClient();
        this.storage = new NeoStorage(context);
        this.integrations = new IntegrationsManager(this.apiClient, this.storage);
        vscode.window.onDidCloseTerminal(t => {
            if (t === this.terminal) { this.terminal = undefined; }
        }, undefined, context.subscriptions);
        // Read-only scheme serving pre-run file content for diff previews
        context.subscriptions.push(
            vscode.workspace.registerTextDocumentContentProvider('agent-neo-prerun', {
                provideTextDocumentContent: uri => this.providePreRunContent(uri)
            })
        );
    }

    /**
     * Post a message to whichever chat surface is live (sidebar preferred).
     */
    private post(message: any) {
        (this.view ?? this.panel)?.webview.postMessage(message);
    }

    /**
     * Sidebar entry point — called by VS Code when the Agent NEO view
     * in the activity bar is first revealed.
     */
    public resolveWebviewView(webviewView: vscode.WebviewView) {
        this.view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this.getWebviewContent();
        webviewView.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            undefined,
            this.context.subscriptions
        );
        webviewView.onDidDispose(() => {
            if (this.view === webviewView) { this.view = undefined; }
        });
        void this.initWorkspaceInfo();
    }

    /**
     * Show the chat — focuses the sidebar view; falls back to an editor
     * panel if the view cannot be resolved (e.g. older VS Code).
     */
    public show() {
        vscode.commands.executeCommand(`${ChatPanel.viewId}.focus`).then(
            undefined,
            () => this.showPanel()
        );
    }

    /**
     * Legacy editor-panel surface (fallback when the sidebar is unavailable).
     */
    private showPanel() {
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
        });

        this.panel.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            undefined,
            this.context.subscriptions
        );
        void this.initWorkspaceInfo();
    }

    /**
     * Get or create the dedicated "Agent NEO" integrated terminal.
     */
    public openTerminal(): vscode.Terminal {
        if (!this.terminal || this.terminal.exitStatus !== undefined) {
            this.terminal = vscode.window.createTerminal({ name: 'Agent NEO' });
        }
        this.terminal.show(true);
        return this.terminal;
    }

    /**
     * Run a command in the Agent NEO terminal (user-initiated from a card).
     */
    private runInTerminal(command: string) {
        if (!command) { return; }
        this.openTerminal().sendText(command, true);
    }

    /**
     * Send a message to the chat (called from commands).
     */
    public async sendMessage(message: string, context?: any) {
        if (!this.view && !this.panel) {
            this.show();
            // Give the sidebar webview a moment to resolve before posting
            await new Promise(resolve => setTimeout(resolve, 600));
        }

        // Send message to webview to display
        this.post({
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
                await this.handleSendMessage(message.message, message.context, message.attachmentIds, message.model);
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
                void this.initWorkspaceInfo();
                void this.sendModelList();
                break;
            case 'openFile':
                await this._revealFile(message.path);
                break;
            case 'runInTerminal':
                this.runInTerminal(message.command);
                break;
            case 'openNeoTerminal':
                this.openTerminal();
                break;
            case 'getSettingsInfo':
                await this.handleGetSettingsInfo();
                break;
            case 'openVSCodeSettings':
                void vscode.commands.executeCommand('workbench.action.openSettings', 'agentNeo');
                break;
            case 'openDiff':
                await this._openDiff(message.path, message.ref, message.old);
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
                await this.handleAutoRun(message.task, message.model);
                break;
            case 'cloneRepo':
                await this.handleCloneRepo(message.url);
                break;
            case 'manageRepos':
                void vscode.commands.executeCommand('agent-neo.manageRepos');
                break;
            case 'setGitHubToken':
                await vscode.commands.executeCommand('agent-neo.setGitHubToken');
                await this.handleGetSettingsInfo();
                break;
            case 'clearGitHubToken':
                await vscode.commands.executeCommand('agent-neo.clearGitHubToken');
                await this.handleGetSettingsInfo();
                break;
            case 'manageMcpServers':
                await vscode.commands.executeCommand('agent-neo.manageMcpServers');
                await this.handleGetSettingsInfo();
                break;
            case 'manageCliTools':
                await vscode.commands.executeCommand('agent-neo.manageCliTools');
                await this.handleGetSettingsInfo();
                break;
        }
    }

    /**
     * Handle sending a message to the backend.
     */
    private async handleSendMessage(message: string, context?: any, attachmentIds?: string[], model?: string) {
        try {
            // Show loading state
            this.post({
                type: 'loading',
                loading: true
            });

            // Get current editor context if not provided
            if (!context) {
                context = this.getCurrentContext();
            }

            if (model) { this.selectedModel = model; }

            // Send to backend (with optional attachment IDs)
            const response = await this.apiClient.sendChatMessage(
                message,
                this.sessionId,
                context,
                attachmentIds,
                model || this.selectedModel
            );

            // Update session ID
            this.sessionId = response.session_id;

            // Send response to webview
            this.post({
                type: 'assistantMessage',
                message: response.message,
                actionType: response.action_type,
                diffProposal: response.proposed_diff
            });

        } catch (error: any) {
            console.error('Failed to send message:', error);
            this.post({
                type: 'error',
                message: error.message || 'Failed to send message'
            });
        } finally {
            this.post({
                type: 'loading',
                loading: false
            });
        }
    }

    /**
     * Get current editor context, including VS Code diagnostics (errors/warnings).
     */
    private getCurrentContext(): any {
        const editor = vscode.window.activeTextEditor;
        const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        // Gather diagnostics from all open files (first 20 errors/warnings)
        const diagnostics: string[] = [];
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
    private async loadHistory() {
        if (!this.sessionId) {
            return;
        }

        try {
            const history = await this.apiClient.getChatHistory(this.sessionId);
            this.post({
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
        this.post({
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
            this.post({
                type: 'loading',
                loading: true
            });

            // Call Agent NEO /chat/approve endpoint
            const response = await this.apiClient.approveDiff(this.sessionId!, true, push);

            // Show success message
            vscode.window.showInformationMessage('Changes applied successfully!');

            // Add execution result card to chat
            this.post({
                type: 'executionResult',
                message: response.message,
                executionResult: response.execution_result || null
            });

        } catch (error: any) {
            console.error('Failed to apply changes:', error);
            vscode.window.showErrorMessage(`Failed to apply changes: ${error.message}`);

            this.post({
                type: 'error',
                message: `Failed to apply changes: ${error.message}`
            });
        } finally {
            this.post({
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

            this.post({
                type: 'assistantMessage',
                message: response.message
            });
        } catch (error: any) {
            console.error('Failed to reject diff:', error);
            this.post({
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

                    /* ── Model picker ── */
                    #modelSelect {
                        background: var(--vscode-dropdown-background);
                        color: var(--vscode-dropdown-foreground);
                        border: 1px solid var(--vscode-dropdown-border, transparent);
                        border-radius: 2px;
                        padding: 4px 4px;
                        font-size: 11px;
                        max-width: 150px;
                        cursor: pointer;
                        align-self: center;
                    }

                    #modelSelect:focus {
                        outline: 1px solid var(--vscode-focusBorder);
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

                    /* ── Phase D: workspace strip, run cards, settings ── */
                    #settingsBtn {
                        background: var(--vscode-button-secondaryBackground, var(--vscode-button-background));
                        color: var(--vscode-button-secondaryForeground, var(--vscode-button-foreground));
                        border: none;
                        padding: 4px 8px;
                        cursor: pointer;
                        font-size: 12px;
                        border-radius: 3px;
                    }
                    #settingsBtn:hover { opacity: 0.85; }
                    #wsStrip {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        padding: 3px 16px;
                        font-size: 11px;
                        opacity: 0.8;
                        border-bottom: 1px solid var(--vscode-panel-border);
                        background-color: var(--vscode-sideBar-background);
                    }
                    #wsStrip:empty { display: none; }
                    #wsStrip .ws-item { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                    .neo-card {
                        border: 1px solid var(--vscode-panel-border, #444);
                        border-left: 3px solid var(--vscode-textLink-foreground, #4daafc);
                        border-radius: 4px;
                        background: var(--vscode-editorWidget-background, rgba(128,128,128,0.08));
                        padding: 7px 10px;
                        margin: 6px 0;
                        font-size: 12px;
                    }
                    .neo-card.ok { border-left-color: var(--vscode-testing-iconPassed, #2ea043); }
                    .neo-card.warn { border-left-color: var(--vscode-editorWarning-foreground, #d29922); }
                    .neo-card.err { border-left-color: var(--vscode-editorError-foreground, #f85149); }
                    .neo-card-title { font-weight: 600; margin-bottom: 3px; }
                    .neo-card-body { opacity: 0.9; white-space: pre-wrap; }
                    .file-chip {
                        display: inline-block;
                        margin: 2px 4px 2px 0;
                        padding: 1px 7px;
                        border-radius: 9px;
                        font-size: 11px;
                        font-family: var(--vscode-editor-font-family, monospace);
                        background: var(--vscode-badge-background, #4d4d4d);
                        color: var(--vscode-badge-foreground, #fff);
                        cursor: pointer;
                    }
                    .file-chip:hover { opacity: 0.8; text-decoration: underline; }
                    .task-progress { margin: 4px 0; }
                    .phase-row { padding: 2px 0; opacity: 0.65; }
                    .phase-row.active { opacity: 1; font-weight: 600; }
                    .phase-row.done { opacity: 0.9; }
                    .phase-row .phase-summary {
                        font-weight: 400;
                        opacity: 0.8;
                        font-size: 11px;
                        display: block;
                        padding-left: 20px;
                    }
                    .term-card {
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        margin: 4px 0;
                        font-family: var(--vscode-editor-font-family, monospace);
                    }
                    .term-card code { flex: 1; overflow-x: auto; white-space: nowrap; }
                    .term-run-btn {
                        border: 1px solid var(--vscode-button-border, transparent);
                        background: var(--vscode-button-secondaryBackground, #3a3d41);
                        color: var(--vscode-button-secondaryForeground, #fff);
                        border-radius: 3px;
                        padding: 1px 8px;
                        font-size: 11px;
                        cursor: pointer;
                        white-space: nowrap;
                    }
                    .term-run-btn:hover { opacity: 0.85; }
                    #settingsView {
                        display: none;
                        position: fixed;
                        inset: 0;
                        z-index: 100;
                        background: var(--vscode-editor-background, #1e1e1e);
                        overflow-y: auto;
                        padding: 12px 16px;
                    }
                    #settingsView.open { display: block; }
                    #settingsView h2 { margin: 0; font-size: 15px; }
                    .settings-head {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 10px;
                    }
                    .settings-section {
                        border: 1px solid var(--vscode-panel-border, #444);
                        border-radius: 4px;
                        padding: 8px 10px;
                        margin-bottom: 10px;
                    }
                    .settings-section h3 {
                        margin: 0 0 6px;
                        font-size: 11px;
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                        opacity: 0.8;
                    }
                    .settings-row {
                        display: flex;
                        justify-content: space-between;
                        gap: 8px;
                        padding: 2px 0;
                        font-size: 12px;
                    }
                    .settings-row .sr-key { opacity: 0.75; }
                    .settings-pill {
                        display: inline-block;
                        padding: 0 8px;
                        border-radius: 8px;
                        font-size: 11px;
                        background: var(--vscode-badge-background, #4d4d4d);
                        color: var(--vscode-badge-foreground, #fff);
                    }
                    .settings-pill.ok { background: var(--vscode-testing-iconPassed, #2ea043); color: #fff; }
                    .settings-pill.err { background: var(--vscode-editorError-foreground, #f85149); color: #fff; }
                    .settings-btn {
                        border: 1px solid var(--vscode-button-border, transparent);
                        background: var(--vscode-button-secondaryBackground, #3a3d41);
                        color: var(--vscode-button-secondaryForeground, #fff);
                        border-radius: 3px;
                        padding: 2px 10px;
                        font-size: 12px;
                        cursor: pointer;
                    }
                    .settings-btn:hover { opacity: 0.85; }
                    .settings-file { cursor: pointer; color: var(--vscode-textLink-foreground); }
                    .settings-file:hover { text-decoration: underline; }
                    /* ── Polish: per-file stats + run history ── */
                    .chip-stat { margin-left: 5px; font-size: 10px; }
                    .chip-stat .ca { color: var(--vscode-gitDecoration-addedResourceForeground, #2ea043); }
                    .chip-stat .cr { color: var(--vscode-gitDecoration-deletedResourceForeground, #f85149); }
                    #runHistory {
                        display: none;
                        padding: 2px 10px 4px;
                        border-bottom: 1px solid var(--vscode-panel-border, #333);
                        font-size: 12px;
                        flex-shrink: 0;
                    }
                    .run-head { cursor: pointer; opacity: 0.8; padding: 3px 0; user-select: none; }
                    .run-head:hover { opacity: 1; }
                    .run-row {
                        cursor: pointer;
                        padding: 2px 6px;
                        border-radius: 3px;
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }
                    .run-row:hover { background: var(--vscode-list-hoverBackground, #2a2d2e); }
                    .run-row.active {
                        background: var(--vscode-list-activeSelectionBackground, #094771);
                        color: var(--vscode-list-activeSelectionForeground, #fff);
                    }
                    .run-flash { outline: 2px solid var(--vscode-focusBorder, #007fd4); }
                    .chip-badge {
                        margin-left: 5px;
                        font-size: 9px;
                        padding: 0 4px;
                        border-radius: 6px;
                        text-transform: uppercase;
                        background: var(--vscode-badge-background, #4d4d4d);
                        color: var(--vscode-badge-foreground, #fff);
                    }
                    .chip-badge.del { background: var(--vscode-editorError-foreground, #f85149); color: #fff; }
                    .settings-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
                    .settings-tab {
                        cursor: pointer;
                        padding: 2px 8px;
                        border-radius: 8px;
                        font-size: 11px;
                        background: var(--vscode-button-secondaryBackground, #3a3d41);
                        color: var(--vscode-button-secondaryForeground, #fff);
                    }
                    .settings-tab.active {
                        background: var(--vscode-button-background, #0e639c);
                        color: var(--vscode-button-foreground, #fff);
                    }
                </style>
            </head>
            <body>
                <div id="header">
                    <h1>Agent NEO Chat</h1>
                    <div id="headerActions">
                        <button id="newThreadBtn" title="Summarise this thread and start fresh">🔄 New Thread</button>
                        <button id="clearBtn">Clear Session</button>
                        <button id="settingsBtn" title="Agent NEO settings">⚙️</button>
                    </div>
                </div>
                <div id="wsStrip"></div>
                <div id="runHistory"></div>

                <div id="settingsView">
                    <div class="settings-head">
                        <h2>⚙️ Agent NEO Settings</h2>
                        <button class="settings-btn" data-action="close">✕ Close</button>
                    </div>
                    <div id="settingsBody"><em>Loading…</em></div>
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
                    <select id="modelSelect" title="Model for this run"></select>
                    <button id="sendBtn">Send</button>
                </div>

                <script>
                    const vscode = acquireVsCodeApi();
                    const messagesDiv = document.getElementById('messages');
                    const messageInput = document.getElementById('messageInput');
                    const modelSelect = document.getElementById('modelSelect');
                    const sendBtn = document.getElementById('sendBtn');
                    const clearBtn = document.getElementById('clearBtn');
                    const newThreadBtn = document.getElementById('newThreadBtn');
                    const attachBtn = document.getElementById('attachBtn');
                    const fileInput = document.getElementById('fileInput');
                    const micBtn = document.getElementById('micBtn');
                    const suggestionsContainer = document.getElementById('suggestionsContainer');
                    const attachmentPreview = document.getElementById('attachmentPreview');
                    const wsStrip = document.getElementById('wsStrip');
                    const runHistory = document.getElementById('runHistory');
                    const settingsView = document.getElementById('settingsView');
                    const settingsBody = document.getElementById('settingsBody');
                    const settingsBtn = document.getElementById('settingsBtn');

                    // ── Phase D: run-state tracking + card helpers ──
                    let runState = null;      // per-run summary data, reset on streamRunStart
                    let lastContext = null;   // last context_ready payload (shown in settings)

                    // ── Polish: persisted webview state (survives reload/hide) ──
                    const persisted = vscode.getState() || {};
                    let threads = persisted.threads || [];           // recent runs, newest first
                    let activeThreadId = persisted.activeThreadId || null;
                    let historyOpen = persisted.historyOpen || false;
                    let settingsSection = persisted.settingsSection || 'integrations';
                    let selectedModel = persisted.selectedModel || '';  // '' → backend default
                    let lastSettingsInfo = null;   // last settingsInfo payload, for tab re-renders
                    if (persisted.lastContext) { lastContext = persisted.lastContext; }
                    // A run left 'running' by a window reload can never complete —
                    // its stream is gone, so present it as interrupted.
                    threads.forEach(t => { if (t.status === 'running') { t.status = 'interrupted'; } });

                    function saveState() {
                        try {
                            let kids = Array.prototype.slice.call(messagesDiv.children, -60);
                            let html = kids.map(k => k.outerHTML).join('');
                            // cap size by dropping whole oldest cards (never slice mid-tag)
                            while (html.length > 200000 && kids.length > 1) {
                                kids = kids.slice(1);
                                html = kids.map(k => k.outerHTML).join('');
                            }
                            vscode.setState({
                                html: html,
                                ws: wsStrip.innerHTML,
                                threads: threads,
                                activeThreadId: activeThreadId,
                                historyOpen: historyOpen,
                                settingsOpen: settingsView.classList.contains('open'),
                                settingsSection: settingsSection,
                                selectedModel: selectedModel,
                                lastContext: lastContext
                            });
                        } catch (e) { /* state save is best-effort */ }
                    }
                    let saveTimer = null;
                    function scheduleSaveState() {
                        clearTimeout(saveTimer);
                        saveTimer = setTimeout(saveState, 400);
                    }

                    // ── Model picker ──
                    // Fill the dropdown from the backend catalog; fall back to a
                    // small built-in list when the backend hasn't answered yet.
                    function fmtPrice(v) {
                        if (v == null) { return null; }
                        return '$' + (Math.round(v * 100) / 100);
                    }
                    function populateModels(catalog) {
                        let items = catalog;
                        if (!items || !items.length) {
                            items = [
                                { id: 'claude-sonnet', label: 'Claude Sonnet 4', input_per_mtok: 3, output_per_mtok: 15 },
                                { id: 'claude-opus', label: 'Claude Opus 4', input_per_mtok: 15, output_per_mtok: 75 },
                                { id: 'gpt-4o', label: 'GPT-4o', input_per_mtok: 2.5, output_per_mtok: 10 },
                                { id: 'o1', label: 'OpenAI o1', input_per_mtok: 15, output_per_mtok: 60 }
                            ];
                        }
                        let h = '<option value="">Default</option>';
                        items.forEach(m => {
                            let label = m.label || m.id;
                            let title = label;
                            const pin = fmtPrice(m.input_per_mtok);
                            const pout = fmtPrice(m.output_per_mtok);
                            if (pin != null && pout != null) {
                                label += ' · ' + pin + '/' + pout;
                                title = label + ' per MTok (in/out)';
                            }
                            h += '<option value="' + escAttr(m.id) + '" title="' + escAttr(title) + '">' + escapeHtml(label) + '</option>';
                        });
                        modelSelect.innerHTML = h;
                        modelSelect.value = selectedModel || '';
                        if (modelSelect.value !== (selectedModel || '')) {
                            // saved model no longer offered — fall back to default
                            selectedModel = '';
                            modelSelect.value = '';
                        }
                    }
                    populateModels(null);
                    modelSelect.addEventListener('change', () => {
                        selectedModel = modelSelect.value;
                        scheduleSaveState();
                    });

                    // ── Polish: thread / run history strip ──
                    // Compact metadata line for a history entry (tooltip + archived card)
                    function threadMetaStr(t) {
                        const meta = [];
                        if (t.ts) { meta.push('Started ' + new Date(t.ts).toLocaleString()); }
                        if (t.files != null) { meta.push(t.files + ' file(s)'); }
                        if (t.added || t.removed) { meta.push('+' + (t.added || 0) + ' −' + (t.removed || 0)); }
                        if (t.sha) { meta.push('commit ' + t.sha); }
                        return meta.join(' · ');
                    }

                    function threadIcon(t) {
                        if (t.status === 'running') { return '⏳'; }
                        if (t.status === 'committed') { return '✅'; }
                        if (t.status === 'blocked') { return '⛔'; }
                        if (t.status === 'halted') { return '🛑'; }
                        if (t.status === 'interrupted') { return '⚠️'; }
                        if (t.status === 'error') { return '❌'; }
                        return '☑️';
                    }

                    function renderThreads() {
                        if (!threads.length) { runHistory.innerHTML = ''; runHistory.style.display = 'none'; return; }
                        runHistory.style.display = 'block';
                        let h = '<div class="run-head">' + (historyOpen ? '▾' : '▸') + ' 🕘 Recent runs (' + threads.length + ')</div>';
                        if (historyOpen) {
                            threads.forEach(t => {
                                h += '<div class="run-row' + (t.id === activeThreadId ? ' active' : '') +
                                    '" data-run="' + escAttr(t.id) + '" title="' + escAttr(threadMetaStr(t)) + '">' +
                                    threadIcon(t) + ' ' + escapeHtml(t.task || '(task)') + '</div>';
                            });
                        }
                        runHistory.innerHTML = h;
                    }

                    runHistory.addEventListener('click', (e) => {
                        if (e.target.closest('.run-head')) {
                            historyOpen = !historyOpen;
                            renderThreads();
                            scheduleSaveState();
                            return;
                        }
                        const row = e.target.closest('.run-row');
                        if (!row) return;
                        activeThreadId = row.dataset.run;
                        renderThreads();
                        const card = messagesDiv.querySelector('[data-run-id="' + activeThreadId + '"]');
                        if (card) {
                            card.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            card.classList.add('run-flash');
                            setTimeout(() => card.classList.remove('run-flash'), 1600);
                        } else {
                            // Detailed cards were trimmed — show high-level metadata instead
                            const t = threads.find(x => x.id === activeThreadId);
                            if (t) {
                                const meta = threadMetaStr(t);
                                const wrapper = document.createElement('div');
                                wrapper.className = 'message assistant';
                                wrapper.innerHTML = '<div class="neo-card">' +
                                    '<div class="neo-card-title">🗃️ Archived run — ' + escapeHtml(t.task || '') + '</div>' +
                                    '<div class="neo-card-body">Status: ' + escapeHtml(t.status || 'unknown') +
                                    (meta ? '<br>' + escapeHtml(meta) : '') +
                                    '<br><span style="opacity:.7">Detailed cards for this run were trimmed from the view.</span></div></div>';
                                messagesDiv.appendChild(wrapper);
                                scrollToBottom();
                            }
                        }
                        scheduleSaveState();
                    });

                    function escAttr(s) {
                        return String(s == null ? '' : s)
                            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
                            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    }

                    // files: array of strings or {path, reason} objects → clickable chips.
                    // stats: optional {path: {added, removed, op?, renamedFrom?}} map →
                    //   compact +/- suffix plus deleted/renamed badges.
                    // ref: optional pre-run git ref → chips open a diff instead of the file.
                    function fileChipsHtml(files, stats, ref) {
                        return (files || []).map(f => {
                            const p = typeof f === 'string' ? f : (f.path || '');
                            const reason = (f && typeof f === 'object' && f.reason) ? f.reason : '';
                            const st = stats ? stats[p] : null;
                            const statHtml = (st && (st.added || st.removed))
                                ? ' <span class="chip-stat"><span class="ca">+' + (st.added || 0) + '</span> <span class="cr">−' + (st.removed || 0) + '</span></span>'
                                : '';
                            let badge = '';
                            let oldAttr = '';
                            let title = reason;
                            if (st && st.op === 'deleted') {
                                badge = ' <span class="chip-badge del">deleted</span>';
                                title = title || 'deleted in this run — click to view the pre-run version';
                            } else if (st && st.op === 'renamed') {
                                badge = ' <span class="chip-badge">renamed</span>';
                                if (st.renamedFrom) {
                                    title = title || ('renamed from ' + st.renamedFrom);
                                    oldAttr = '" data-old="' + escAttr(st.renamedFrom);
                                }
                            }
                            const refAttr = ref ? '" data-ref="' + escAttr(ref) : '';
                            return '<span class="file-chip" data-path="' + escAttr(p) + refAttr + oldAttr +
                                '" title="' + escAttr(title) + '">' + escapeHtml(p) + statHtml + badge + '</span>';
                        }).join('');
                    }

                    // Append a progress card inside the live run card (or chat as fallback)
                    function appendRunCard(html, cls) {
                        const target = document.getElementById('srSteps') || messagesDiv;
                        const div = document.createElement('div');
                        div.className = 'neo-card' + (cls ? ' ' + cls : '');
                        div.innerHTML = html;
                        target.appendChild(div);
                        scrollToBottom();
                        return div;
                    }

                    function trackFiles(files) {
                        if (!runState || !files) return;
                        files.forEach(f => {
                            const p = typeof f === 'string' ? f : (f.path || '');
                            if (p && !runState.files[p]) { runState.files[p] = { added: 0, removed: 0 }; }
                        });
                    }

                    settingsBtn.addEventListener('click', () => {
                        settingsView.classList.add('open');
                        vscode.postMessage({ type: 'getSettingsInfo' });
                        scheduleSaveState();
                    });

                    settingsView.addEventListener('click', (e) => {
                        const tab = e.target.closest('.settings-tab');
                        if (tab && tab.dataset.section) {
                            settingsSection = tab.dataset.section;
                            if (lastSettingsInfo) { renderSettings(lastSettingsInfo); }
                            scheduleSaveState();
                            return;
                        }
                        const chip = e.target.closest('.file-chip');
                        if (chip && chip.dataset.path) {
                            vscode.postMessage({ type: 'openFile', path: chip.dataset.path });
                            return;
                        }
                        const el = e.target.closest('[data-action]');
                        if (!el) return;
                        const action = el.dataset.action;
                        if (action === 'close') { settingsView.classList.remove('open'); scheduleSaveState(); }
                        else if (action === 'vscodeSettings') { vscode.postMessage({ type: 'openVSCodeSettings' }); }
                        else if (action === 'neoTerminal') { vscode.postMessage({ type: 'openNeoTerminal' }); }
                        else if (action === 'openFile') { vscode.postMessage({ type: 'openFile', path: el.dataset.path }); }
                        else if (action === 'manageRepos') { vscode.postMessage({ type: 'manageRepos' }); }
                        else if (action === 'setGitHubToken') { vscode.postMessage({ type: 'setGitHubToken' }); }
                        else if (action === 'clearGitHubToken') { vscode.postMessage({ type: 'clearGitHubToken' }); }
                        else if (action === 'manageMcpServers') { vscode.postMessage({ type: 'manageMcpServers' }); }
                        else if (action === 'manageCliTools') { vscode.postMessage({ type: 'manageCliTools' }); }
                    });

                    // Delegated clicks: file chips open files (or diffs), ▶ buttons run commands
                    messagesDiv.addEventListener('click', (e) => {
                        const chip = e.target.closest('.file-chip');
                        if (chip && chip.dataset.path) {
                            if (chip.dataset.ref) {
                                vscode.postMessage({ type: 'openDiff', path: chip.dataset.path, ref: chip.dataset.ref, old: chip.dataset.old });
                            } else {
                                vscode.postMessage({ type: 'openFile', path: chip.dataset.path });
                            }
                            return;
                        }
                        const runBtn = e.target.closest('.term-run-btn');
                        if (runBtn && runBtn.dataset.cmd) {
                            vscode.postMessage({ type: 'runInTerminal', command: runBtn.dataset.cmd });
                        }
                    });

                    function renderSettings(info) {
                        lastSettingsInfo = info;
                        const sections = {};
                        let h = '';
                        h += '<div class="settings-section"><h3>Integrations</h3>';
                        h += '<div class="settings-row"><span class="sr-key">Backend API</span><span>' + escapeHtml(info.apiUrl || '') + '</span></div>';
                        h += '<div class="settings-row"><span class="sr-key">Health</span>' +
                            (info.healthy ? '<span class="settings-pill ok">connected</span>' : '<span class="settings-pill err">unreachable</span>') + '</div>';
                        h += '<div class="settings-row"><span class="sr-key">API token</span><span>' + (info.tokenSet ? 'configured' : 'not set') + '</span></div>';
                        h += '<div class="settings-row"><button class="settings-btn" data-action="vscodeSettings">Open VS Code settings</button></div>';
                        h += '</div>';

                        h += '<div class="settings-section"><h3>MCP servers</h3>';
                        const mcps = info.mcpServers || [];
                        if (mcps.length) {
                            mcps.forEach(s => {
                                h += '<div class="settings-row"><span class="sr-key">' + escapeHtml(s.name || '') + '</span>' +
                                    (s.enabled ? '<span class="settings-pill ok">enabled</span>' : '<span class="settings-pill err">disabled</span>') + '</div>';
                                const meta = [];
                                meta.push(s.transport === 'http' ? 'remote (HTTP)' : 'local (stdio)');
                                if (s.last_refresh_ok === true) { meta.push('✓ ' + (s.tools || []).length + ' tool(s)'); }
                                else if (s.last_refresh_ok === false) { meta.push('✗ ' + (s.last_refresh_error || 'unreachable')); }
                                else { meta.push('not tested yet'); }
                                const bindings = Object.keys(s.secret_env || {});
                                if (bindings.length) { meta.push('secrets: ' + bindings.join(', ')); }
                                h += '<div class="settings-row"><span class="sr-key" style="opacity:.55;font-size:11px">' + escapeHtml(meta.join('  ·  ')) + '</span></div>';
                            });
                        } else {
                            h += '<div class="settings-row"><span class="sr-key">No MCP servers yet — add a local (stdio) or remote (HTTP) server.</span></div>';
                        }
                        h += '<div class="settings-row"><button class="settings-btn" data-action="manageMcpServers">Manage MCP servers…</button></div>';
                        h += '</div>';

                        h += '<div class="settings-section"><h3>CLI tools</h3>';
                        const clis = info.cliTools || [];
                        if (clis.length) {
                            clis.forEach(t => {
                                h += '<div class="settings-row"><span class="sr-key">' + escapeHtml(t.name || '') + '</span>' +
                                    (t.enabled ? '<span class="settings-pill ok">enabled</span>' : '<span class="settings-pill err">disabled</span>') + '</div>';
                                const meta = [];
                                meta.push(t.available ? '✓ available' : '✗ not on PATH');
                                meta.push((t.allowed_subcommands || []).length ? 'allowlist: ' + t.allowed_subcommands.join(', ') : 'all subcommands');
                                h += '<div class="settings-row"><span class="sr-key" style="opacity:.55;font-size:11px">' + escapeHtml(meta.join('  ·  ')) + '</span></div>';
                            });
                        } else {
                            h += '<div class="settings-row"><span class="sr-key">No CLI tools yet — register one to expose it to the agent (governed, never a raw shell).</span></div>';
                        }
                        h += '<div class="settings-row"><button class="settings-btn" data-action="manageCliTools">Manage CLI tools…</button></div>';
                        h += '</div>';
                        sections.integrations = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Repos</h3>';
                        const mrepos = info.managedRepos || [];
                        if (mrepos.length) {
                            mrepos.forEach(r => {
                                const isActive = r.id === info.activeRepoId;
                                h += '<div class="settings-row"><span class="sr-key">' + (isActive ? '✓ ' : '') + escapeHtml(r.name || '') + (isActive ? ' <span class="settings-pill ok">active</span>' : '') + '</span></div>';
                                h += '<div class="settings-row"><span class="sr-key" style="opacity:.7">' + escapeHtml(r.path || '') + '</span></div>';
                                const meta = [];
                                if (r.default_branch) { meta.push('branch: ' + r.default_branch); }
                                meta.push(r.remote_url ? 'remote: ' + r.remote_url : 'no remote');
                                meta.push(r.last_indexed_at ? 'indexed: ' + String(r.last_indexed_at).slice(0, 19).replace('T', ' ') : 'not indexed');
                                h += '<div class="settings-row"><span class="sr-key" style="opacity:.55;font-size:11px">' + escapeHtml(meta.join('  ·  ')) + '</span></div>';
                            });
                        } else {
                            h += '<div class="settings-row"><span class="sr-key">No managed repos yet — add a local repo or clone one from GitHub.</span></div>';
                        }
                        h += '<div class="settings-row"><button class="settings-btn" data-action="manageRepos">Manage repos…</button></div>';
                        h += '<div class="settings-row"><span class="sr-key">GitHub token</span><span>' + (info.githubTokenSet ? '<span class="settings-pill ok">configured</span>' : 'not set') + '</span></div>';
                        h += '<div class="settings-row">';
                        h += '<button class="settings-btn" data-action="setGitHubToken">' + (info.githubTokenSet ? 'Update token' : 'Set token') + '</button> ';
                        if (info.githubTokenSet) { h += '<button class="settings-btn" data-action="clearGitHubToken">Clear token</button>'; }
                        h += '</div>';
                        h += '<div class="settings-row"><span class="sr-key" style="opacity:.55;font-size:11px">Stored in VS Code SecretStorage. Used only when cloning private repos.</span></div>';
                        h += '</div>';
                        sections.repos = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Rules &amp; Guidelines</h3>';
                        if ((info.guidelineFiles || []).length) {
                            info.guidelineFiles.forEach(name => {
                                h += '<div class="settings-row"><span class="settings-file" data-action="openFile" data-path="' + escAttr(name) + '">📄 ' + escapeHtml(name) + '</span></div>';
                            });
                        } else {
                            h += '<div class="settings-row"><span class="sr-key">No guideline files (.neo, .neo.md, AGENT.md) found in the workspace root.</span></div>';
                        }
                        h += '</div>';
                        sections.rules = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Context</h3>';
                        if (lastContext) {
                            h += '<div class="settings-row"><span class="sr-key">Last context pack</span><span>' + (lastContext.files || []).length + ' file(s)</span></div>';
                            h += '<div>' + fileChipsHtml(lastContext.files) + '</div>';
                        } else {
                            h += '<div class="settings-row"><span class="sr-key">Context packs appear here after an AutoRun starts.</span></div>';
                        }
                        h += '</div>';
                        sections.context = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Terminal</h3>';
                        h += '<div class="settings-row"><span class="sr-key">Commands suggested by the agent run in a dedicated "Agent NEO" terminal.</span></div>';
                        h += '<div class="settings-row"><button class="settings-btn" data-action="neoTerminal">Open Agent NEO terminal</button></div>';
                        h += '</div>';
                        sections.terminal = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Workspace</h3>';
                        h += '<div class="settings-row"><span class="sr-key">Folder</span><span>' + escapeHtml(info.workspace || '—') + '</span></div>';
                        h += '<div class="settings-row"><span class="sr-key">Path</span><span>' + escapeHtml(info.workspacePath || '—') + '</span></div>';
                        h += '<div class="settings-row"><span class="sr-key">Branch</span><span>' + escapeHtml(info.branch || '—') + '</span></div>';
                        h += '<div class="settings-row"><span class="sr-key">Pending changes</span><span>' + (info.dirty == null ? '—' : info.dirty) + '</span></div>';
                        h += '</div>';
                        sections.workspace = h;
                        h = '';

                        h += '<div class="settings-section"><h3>Account &amp; Preferences</h3>';
                        h += '<div class="settings-row"><span class="sr-key">All Agent NEO preferences (API URL, token, model) live under the agentNeo.* settings namespace.</span></div>';
                        h += '<div class="settings-row"><button class="settings-btn" data-action="vscodeSettings">Manage preferences</button></div>';
                        h += '</div>';
                        sections.account = h;

                        const labels = { integrations: 'Integrations', repos: 'Repos', rules: 'Rules &amp; Guidelines', context: 'Context', terminal: 'Terminal', workspace: 'Workspace', account: 'Account &amp; Preferences' };
                        if (!sections[settingsSection]) { settingsSection = 'integrations'; }
                        let tabs = '<div class="settings-tabs">';
                        Object.keys(labels).forEach(k => {
                            tabs += '<span class="settings-tab' + (k === settingsSection ? ' active' : '') + '" data-section="' + k + '">' + labels[k] + '</span>';
                        });
                        tabs += '</div>';
                        settingsBody.innerHTML = tabs + sections[settingsSection];
                    }

                    let isLoading = false;
                    let messageCount = 0;           // track thread length
                    const NEW_THREAD_THRESHOLD = 20; // suggest new thread after N messages
                    // SLICE 6 — pending attachments accumulate until message is sent
                    let pendingAttachmentIds = [];
                    // ── Auto-resize textarea ──
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
                                vscode.postMessage({ type: 'autoRun', task, model: selectedModel || undefined });
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

                        // Clear input
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

                        // Action-first: every non-slash message triggers the streaming agent loop
                        // so the agent immediately starts working with tools instead of chatting.
                        vscode.postMessage({ type: 'autoRun', task: message, model: selectedModel || undefined });
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
                        scheduleSaveState();
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
                                threads = [];
                                activeThreadId = null;
                                renderThreads();
                                scheduleSaveState();
                                break;

                            case 'loadHistory':
                                messagesDiv.innerHTML = '';
                                messageCount = 0;
                                threads = [];
                                activeThreadId = null;
                                renderThreads();
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
                                // Any thread still 'running' here lost its stream — mark interrupted
                                threads.forEach(t => { if (t.status === 'running') { t.status = 'interrupted'; } });
                                const runId = 'run_' + Date.now();
                                threads.unshift({ id: runId, task: (message.task || '').slice(0, 80), ts: Date.now(), status: 'running' });
                                threads = threads.slice(0, 10);
                                activeThreadId = runId;
                                renderThreads();
                                runState = {
                                    runId: runId, preRunRef: message.preRunRef || null,
                                    files: {}, commits: [], repairAttempts: 0,
                                    blocked: false, reverted: false, halted: false,
                                    haltReason: '', verification: null, error: false
                                };
                                // Create a live card element we'll update in-place
                                const card = document.createElement('div');
                                card.className = 'message assistant';
                                card.id = 'streamRunCard';
                                card.dataset.runId = runId;
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

                                // ── Context (Phase B) ──
                                } else if (ev.type === 'context_ready') {
                                    lastContext = ev;
                                    appendRunCard(
                                        '<div class="neo-card-title">📚 Context gathered</div>' +
                                        (ev.summary ? '<div class="neo-card-body">' + escapeHtml(ev.summary) + '</div>' : '') +
                                        '<div>' + fileChipsHtml(ev.files) + '</div>'
                                    );

                                // ── Phased planning / task progress ──
                                } else if (ev.type === 'planning') {
                                    if (headerEl) { headerEl.innerHTML = '🧭 <strong>Planning:</strong> ' + escapeHtml(ev.task || ''); }
                                } else if (ev.type === 'phase_plan') {
                                    let rows = '';
                                    (ev.phases || []).forEach((p, i) => {
                                        rows += '<div class="phase-row" id="phase_row_' + escAttr(p.id) + '">⬜ ' + (i + 1) + '. ' + escapeHtml(p.name || p.id) +
                                            (p.specialist ? ' <span style="opacity:.6">(' + escapeHtml(p.specialist) + ')</span>' : '') + '</div>';
                                    });
                                    appendRunCard('<div class="neo-card-title">🗂️ Plan — ' + (ev.phases || []).length + ' phase(s)</div>' +
                                        '<div class="task-progress">' + rows + '</div>');
                                } else if (ev.type === 'phase_start') {
                                    const row = document.getElementById('phase_row_' + ev.phase_id);
                                    const num = typeof ev.phase_index === 'number' ? (ev.phase_index + 1) : '?';
                                    if (row) {
                                        row.classList.add('active');
                                        row.innerHTML = '▶️ ' + num + '. ' + escapeHtml(ev.phase_name || ev.phase_id || '') +
                                            (ev.specialist ? ' <span style="opacity:.6">(' + escapeHtml(ev.specialist) + ')</span>' : '');
                                    }
                                    if (headerEl) {
                                        headerEl.innerHTML = '⚙️ <strong>Phase ' + num + '/' + (ev.total_phases || '?') + ':</strong> ' + escapeHtml(ev.phase_name || '');
                                    }
                                    scrollToBottom();
                                } else if (ev.type === 'phase_end') {
                                    const row = document.getElementById('phase_row_' + ev.phase_id);
                                    if (row) {
                                        row.classList.remove('active');
                                        row.classList.add('done');
                                        row.innerHTML = '✅ ' + escapeHtml(ev.phase_name || ev.phase_id || '') +
                                            (ev.summary ? '<span class="phase-summary">' + escapeHtml((ev.summary || '').slice(0, 200)) + '</span>' : '');
                                    }
                                } else if (ev.type === 'phase_checkpoint') {
                                    trackFiles(ev.files);
                                    if (runState && ev.commit_sha) { runState.commits.push(ev.commit_sha); }
                                    appendRunCard('<div class="neo-card-title">🔖 Phase checkpoint — ' + escapeHtml((ev.commit_sha || '').slice(0, 8)) + '</div>' +
                                        '<div>' + fileChipsHtml(ev.files, runState && runState.files) + '</div>', 'ok');

                                // ── Tool activity ──
                                } else if (ev.type === 'tool_start' && stepsEl) {
                                    const row = document.createElement('div');
                                    row.className = 'auto-run-step';
                                    row.id = 'sr_tool_' + (ev.tool || 'unknown');
                                    const detail = ev.path || ev.command || ev.query || '';
                                    row.innerHTML = '🔧 <strong>' + escapeHtml(ev.tool || '') + '</strong>' +
                                        (detail ? ' <span style="opacity:.7">' + escapeHtml(String(detail).slice(0, 80)) + '</span>' : '') +
                                        ' <span style="opacity:.6">running…</span>';
                                    stepsEl.appendChild(row);
                                    scrollToBottom();
                                } else if (ev.type === 'tool_end' && stepsEl) {
                                    const existing = document.getElementById('sr_tool_' + ev.tool);
                                    const ms = ev.duration_ms ? ' (' + ev.duration_ms + 'ms)' : '';
                                    const row = existing || document.createElement('div');
                                    row.className = 'auto-run-step step-success';
                                    if (ev.tool === 'run_command' && ev.command) {
                                        // Terminal action card — user can replay in the Agent NEO terminal
                                        row.innerHTML = '✅ <strong>run_command</strong>' + ms +
                                            '<div class="term-card"><code>' + escapeHtml(ev.command) + '</code>' +
                                            '<button class="term-run-btn" data-cmd="' + escAttr(ev.command) + '">▶ Run in terminal</button></div>' +
                                            (ev.result ? '<span class="step-msg">' + escapeHtml((ev.result || '').slice(0, 120)) + '</span>' : '');
                                    } else {
                                        const detail = ev.path || ev.query || '';
                                        const snippet = (ev.result || '').slice(0, 120);
                                        row.innerHTML = '✅ <strong>' + escapeHtml(ev.tool || '') + '</strong>' +
                                            (detail ? ' <span style="opacity:.7">' + escapeHtml(String(detail).slice(0, 80)) + '</span>' : '') + ms +
                                            (snippet ? '<br><span class="step-msg">' + escapeHtml(snippet) + '</span>' : '');
                                    }
                                    if (!existing) { stepsEl.appendChild(row); }
                                    if (ev.tool === 'write_file' && ev.path) {
                                        trackFiles([ev.path]);
                                        const st = runState && runState.files[ev.path];
                                        if (st) {
                                            st.added += (ev.lines_added || 0);
                                            st.removed += (ev.lines_removed || 0);
                                        }
                                    } else if ((ev.tool === 'delete_file' || ev.tool === 'rename_file') && ev.path &&
                                               (ev.result || '').indexOf('[error]') !== 0) {
                                        trackFiles([ev.path]);
                                        const st = runState && runState.files[ev.path];
                                        if (st && ev.tool === 'delete_file') { st.op = 'deleted'; }
                                        if (st && ev.tool === 'rename_file') {
                                            st.op = 'renamed';
                                            st.renamedFrom = ev.renamed_from || '';
                                        }
                                    }
                                    scrollToBottom();

                                // ── Verification + repair (Phase C) ──
                                } else if (ev.type === 'verification_started') {
                                    appendRunCard('<div class="neo-card-title">🧪 Verification running…</div>');
                                } else if (ev.type === 'verification_passed') {
                                    appendRunCard('<div class="neo-card-title">🧪 Verification passed</div>' +
                                        '<div class="neo-card-body">' + (ev.checks_run || []).length + ' check(s), ' + (ev.repair_attempts || 0) + ' repair attempt(s)</div>', 'ok');
                                } else if (ev.type === 'verification_failed') {
                                    appendRunCard('<div class="neo-card-title">🧪 Verification failed</div>' +
                                        '<div class="neo-card-body">' + escapeHtml((ev.failure_summary || '').slice(0, 400)) + '</div>', 'err');
                                } else if (ev.type === 'repair_started') {
                                    if (runState) { runState.repairAttempts = ev.attempt || (runState.repairAttempts + 1); }
                                    appendRunCard('<div class="neo-card-title">🔧 Repair attempt ' + (ev.attempt || '?') + '/' + (ev.max_repair_attempts || '?') + '…</div>', 'warn');
                                } else if (ev.type === 'repair_succeeded') {
                                    appendRunCard('<div class="neo-card-title">🔧 Repair attempt ' + (ev.attempt || '?') + ' succeeded</div>', 'ok');
                                } else if (ev.type === 'repair_exhausted') {
                                    appendRunCard('<div class="neo-card-title">🔧 Repair attempts exhausted (' + (ev.repair_attempts || 0) + '/' + (ev.max_repair_attempts || '?') + ')</div>' +
                                        '<div class="neo-card-body">' + escapeHtml((ev.failure_summary || '').slice(0, 400)) + '</div>', 'err');
                                } else if (ev.type === 'verification_summary') {
                                    if (runState) { runState.verification = ev; }

                                // ── Gate / outcome (Phase A) ──
                                } else if (ev.type === 'change_set_blocked') {
                                    if (runState) { runState.blocked = true; runState.reverted = !!ev.reverted; }
                                    trackFiles(ev.files);
                                    appendRunCard(
                                        '<div class="neo-card-title">⛔ Changes blocked by governance</div>' +
                                        '<div class="neo-card-body">' + escapeHtml(((ev.errors || []).join('; ')).slice(0, 400)) + '</div>' +
                                        '<div>' + fileChipsHtml(ev.files) + '</div>' +
                                        (ev.reverted ? '<div class="neo-card-body">↩️ All staged edits were reverted.</div>' : ''),
                                        'err'
                                    );
                                } else if (ev.type === 'run_halted') {
                                    if (runState) {
                                        runState.halted = true;
                                        runState.haltReason = ev.reason || '';
                                        if (ev.reverted) { runState.reverted = true; }
                                    }
                                    appendRunCard('<div class="neo-card-title">🛑 Run halted' + (ev.phase_name ? ' — ' + escapeHtml(ev.phase_name) : '') + '</div>' +
                                        '<div class="neo-card-body">' + escapeHtml(ev.reason || '') + '</div>' +
                                        (ev.reverted ? '<div class="neo-card-body">↩️ Changes reverted.</div>' : ''), 'err');
                                } else if (ev.type === 'no_changes') {
                                    appendRunCard('<div class="neo-card-title">ℹ️ No file changes were made</div>');

                                // ── Run completion ──
                                } else if (ev.type === 'finish') {
                                    trackFiles(ev.files);
                                    if (headerEl) {
                                        headerEl.innerHTML = (ev.success ? '✅' : '❌') + ' <strong>AutoRun done</strong>';
                                    }
                                    if (tokensEl && ev.summary) {
                                        tokensEl.textContent = ev.summary;
                                    }
                                    scrollToBottom();
                                } else if (ev.type === 'commit') {
                                    trackFiles(ev.files);
                                    if (runState && ev.sha) { runState.commits.push(ev.sha); }
                                    const card = document.getElementById('streamRunCard');
                                    if (card) {
                                        const c = document.createElement('div');
                                        c.className = 'auto-run-commit';
                                        c.textContent = '🔖 Committed: ' + (ev.sha || '').slice(0, 8);
                                        card.querySelector('.auto-run-card')?.appendChild(c);
                                    }
                                } else if (ev.type === 'phased_done') {
                                    if (runState && ev.verification) { runState.verification = ev.verification; }
                                    if (headerEl) {
                                        headerEl.innerHTML = '✅ <strong>Phased run complete</strong> — ' + (ev.total_phases || 0) + ' phase(s), ' + (ev.files_written || 0) + ' file(s)';
                                    }
                                    scrollToBottom();
                                } else if (ev.type === 'error') {
                                    if (runState) { runState.error = true; }
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
                                // Final run summary card
                                if (runState) {
                                    const files = Object.keys(runState.files);
                                    let totAdded = 0, totRemoved = 0;
                                    files.forEach(p => {
                                        totAdded += (runState.files[p].added || 0);
                                        totRemoved += (runState.files[p].removed || 0);
                                    });
                                    // Update this run's entry in the history strip
                                    const t = threads.find(x => x.id === runState.runId);
                                    if (t) {
                                        if (runState.blocked) { t.status = 'blocked'; }
                                        else if (runState.halted) { t.status = 'halted'; }
                                        else if (runState.error) { t.status = 'error'; }
                                        else if (runState.commits.length) { t.status = 'committed'; }
                                        else { t.status = 'done'; }
                                        // Durable metadata — survives even after cards are trimmed
                                        t.files = files.length;
                                        t.added = totAdded;
                                        t.removed = totRemoved;
                                        t.sha = (runState.commits[0] || '').slice(0, 8);
                                        renderThreads();
                                    }
                                    const v = runState.verification;
                                    let status;
                                    if (runState.blocked) {
                                        status = '⛔ Blocked by governance' + (runState.reverted ? ' — changes reverted' : '');
                                    } else if (runState.halted) {
                                        status = '🛑 Halted — ' + (runState.haltReason || 'see details above') + (runState.reverted ? ' (changes reverted)' : '');
                                    } else if (runState.error) {
                                        status = '❌ Error — see details above';
                                    } else if (runState.commits.length) {
                                        status = '✅ Committed (' + runState.commits.map(s => (s || '').slice(0, 8)).join(', ') + ')';
                                    } else if (files.length) {
                                        status = '✅ Completed';
                                    } else {
                                        status = 'ℹ️ Finished — no file changes';
                                    }
                                    let h = '<div class="neo-card-title">📋 Run summary</div>';
                                    h += '<div class="neo-card-body">' + escapeHtml(status) + '</div>';
                                    // One-line plain-language recap from tracked run data
                                    const parts = [];
                                    if (files.length) { parts.push('edited ' + files.length + ' file(s) (+' + totAdded + ' −' + totRemoved + ')'); }
                                    if (v && v.final_status) {
                                        parts.push('verification ' + v.final_status +
                                            ((v.repair_attempts || 0) > 0 ? ' after ' + v.repair_attempts + ' repair attempt(s)' : ''));
                                    }
                                    if (runState.commits.length) { parts.push('committed as ' + runState.commits.map(s => (s || '').slice(0, 8)).join(', ')); }
                                    if (runState.reverted) { parts.push('all staged edits were reverted'); }
                                    if (parts.length) {
                                        h += '<div class="neo-card-body" style="opacity:.85">' + escapeHtml('This run ' + parts.join('; ') + '.') + '</div>';
                                    }
                                    if (files.length) {
                                        h += '<div style="margin-top:4px"><strong>Files changed (' + files.length + '):</strong></div>';
                                        h += '<div>' + fileChipsHtml(files, runState.files, runState.preRunRef) + '</div>';
                                    }
                                    if (v) {
                                        h += '<div style="margin-top:4px"><strong>Verification:</strong> ' + escapeHtml(v.final_status || '') +
                                            ' — ' + (v.checks_run || []).length + ' check(s), ' + (v.repair_attempts || 0) + ' repair attempt(s)</div>';
                                        if (v.last_failure_summary) {
                                            h += '<div class="neo-card-body">' + escapeHtml((v.last_failure_summary || '').slice(0, 300)) + '</div>';
                                        }
                                    } else if (runState.repairAttempts) {
                                        h += '<div style="margin-top:4px"><strong>Repair attempts:</strong> ' + runState.repairAttempts + '</div>';
                                    }
                                    const wrapper = document.createElement('div');
                                    wrapper.className = 'message assistant';
                                    const summaryCls = (runState.blocked || runState.halted) ? ' err' : ' ok';
                                    wrapper.innerHTML = '<div class="neo-card' + summaryCls + '">' + h + '</div>';
                                    messagesDiv.appendChild(wrapper);
                                    scrollToBottom();
                                    runState = null;
                                }
                                isLoading = false;
                                sendBtn.disabled = false;
                                break;
                            }

                            // ── Workspace strip (host pushes git/folder info) ──
                            case 'workspaceInfo': {
                                let h = '';
                                if (message.workspace) { h += '<span class="ws-item">📁 ' + escapeHtml(message.workspace) + '</span>'; }
                                if (message.branch) { h += '<span class="ws-item">⎇ ' + escapeHtml(message.branch) + '</span>'; }
                                if (message.dirty != null) {
                                    h += '<span class="ws-item">' + (message.dirty > 0 ? '● ' + message.dirty + ' pending change(s)' : '✓ clean') + '</span>';
                                }
                                wsStrip.innerHTML = h;
                                scheduleSaveState();
                                break;
                            }

                            case 'settingsInfo': {
                                renderSettings(message);
                                break;
                            }

                            // ── Model picker (host pushes configured catalog) ──
                            case 'modelList': {
                                populateModels(message.catalog || []);
                                break;
                            }
                        }
                    });

                    // ── Polish: restore persisted view state before announcing ready ──
                    try {
                        if (persisted.html) {
                            messagesDiv.innerHTML = persisted.html;
                            // strip ids so stale live-run cards can't capture new events
                            messagesDiv.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));
                        }
                        if (persisted.ws) { wsStrip.innerHTML = persisted.ws; }
                        renderThreads();
                        scrollToBottom();
                        if (persisted.settingsOpen) {
                            settingsView.classList.add('open');
                            vscode.postMessage({ type: 'getSettingsInfo' });
                        }
                    } catch (e) { /* restore is best-effort */ }

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
    private async handleNewThread() {
        if (!this.sessionId) { return; }
        try {
            this.post({ type: 'loading', loading: true });
            const result = await this.apiClient.summarizeSession(this.sessionId);

            // Switch the active session
            const oldId = this.sessionId;
            this.sessionId = result.new_session_id;

            vscode.window.showInformationMessage(
                `New thread started (${result.message_count_was} messages summarised).`
            );
            this.post({
                type: 'threadSwitched',
                newSessionId: result.new_session_id,
                summary: result.summary,
                messageCountWas: result.message_count_was,
                oldSessionId: oldId,
            });
        } catch (error: any) {
            vscode.window.showErrorMessage(`Failed to start new thread: ${error.message}`);
            this.post({
                type: 'error',
                message: `Failed to start new thread: ${error.message}`
            });
        } finally {
            this.post({ type: 'loading', loading: false });
        }
    }

    /**
     * Handle "Undo Last Change" rollback request.
     */
    private async handleRollback() {
        if (!this.sessionId) { return; }
        const confirm = await vscode.window.showWarningMessage(
            'This will run git revert on the last applied commit (local only, no push). Continue?',
            'Yes, roll back', 'Cancel'
        );
        if (confirm !== 'Yes, roll back') { return; }

        try {
            this.post({ type: 'loading', loading: true });
            const result = await this.apiClient.rollbackLastChange(this.sessionId);
            const icon = result.success ? '✓' : '✗';
            vscode.window.showInformationMessage(`${icon} ${result.message}`);
            this.post({
                type: 'assistantMessage',
                message: `${icon} **Rollback**: ${result.message}`
            });
        } catch (error: any) {
            vscode.window.showErrorMessage(`Rollback failed: ${error.message}`);
            this.post({
                type: 'error',
                message: `Rollback failed: ${error.message}`
            });
        } finally {
            this.post({ type: 'loading', loading: false });
        }
    }

    /**
     * Handle file attachment upload from webview.
     */
    private async handleUploadAttachment(fileName: string, fileType: 'image' | 'pdf', contentBase64: string) {
        try {
            if (!this.sessionId) {
                // Create a temporary session ID; will be replaced on first chat send
                this.sessionId = `tmp-${Date.now()}`;
            }
            const result = await this.apiClient.uploadAttachment(
                this.sessionId,
                fileName,
                fileType,
                contentBase64
            );
            this.post({
                type: 'attachmentUploaded',
                attachmentId: result.attachment_id,
                fileName: result.file_name,
                fileType: result.file_type
            });
        } catch (error: any) {
            console.error('Attachment upload failed:', error);
            this.post({
                type: 'attachmentError',
                message: `Upload failed: ${error.message}`
            });
        }
    }

    /**
     * Handle suggestions request from webview.
     */
    private async handleGetSuggestions(currentInput: string, context?: any) {
        try {
            const config = vscode.workspace.getConfiguration('agentNeo');
            if (!config.get('enableSuggestions', true)) {
                return;
            }
            const result = await this.apiClient.getSuggestions(currentInput, this.sessionId, context);
            this.post({
                type: 'suggestions',
                suggestions: result.suggestions || []
            });
        } catch (error: any) {
            // Suggestions are non-critical — silently ignore failures
            console.debug('Suggestions request failed:', error.message);
        }
    }

    /**
     * Handle autonomous task run request from webview using SSE streaming.
     * Each event is forwarded to the webview as it arrives so step cards
     * update in real-time instead of waiting for the full loop to finish.
     */
    private async handleAutoRun(task: string, model?: string) {
        if (!task) { return; }

        if (model !== undefined) { this.selectedModel = model; }

        // Echo the user's task into the chat exactly as typed
        this.post({ type: 'userMessage', message: task });
        // Capture the pre-run git ref so summary chips can open diff previews
        const repo = await this._getGitRepo();
        const preRunRef = repo?.state?.HEAD?.commit ?? null;
        // Open a live streaming card in the webview
        this.post({ type: 'streamRunStart', task, preRunRef });

        const context = this.getCurrentContext();
        const { url, token } = this.apiClient.getStreamConfig();

        const body = JSON.stringify({
            task,
            session_id: this.sessionId,
            context,
            model: this.selectedModel || undefined,
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
                if (done) { break; }
                buf += decoder.decode(value, { stream: true });

                // SSE lines are separated by \n\n
                const parts = buf.split('\n\n');
                buf = parts.pop() ?? '';   // keep incomplete tail

                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith('data:')) { continue; }
                    const json = line.slice(5).trim();
                    if (!json || json === '[DONE]') { continue; }
                    try {
                        const event = JSON.parse(json);
                        // Forward every SSE event directly to the webview
                        this.post({ type: 'streamEvent', event });
                        // File reveal: open written files in the VS Code editor
                        if (event.type === 'tool_end' && event.tool === 'write_file' && event.path) {
                            this._revealFile(event.path);
                        }
                    } catch {
                        // malformed chunk — skip
                    }
                }
            }
        } catch (error: any) {
            console.error('AutoRun stream failed:', error);
            this.post({
                type: 'streamEvent',
                event: { type: 'error', error: error.message }
            });
        } finally {
            this.post({ type: 'streamRunDone' });
        }
    }

    /**
     * Open a file written by the agent in the VS Code editor.
     * path is repo-relative; resolved against the current workspace root.
     */
    private async _revealFile(relPath: string) {
        try {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders || workspaceFolders.length === 0) { return; }
            const root = workspaceFolders[0].uri;
            const fileUri = vscode.Uri.joinPath(root, relPath);
            const doc = await vscode.workspace.openTextDocument(fileUri);
            await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: true });
        } catch {
            // file might not be in the current workspace — silently skip
        }
    }

    /**
     * Serve pre-run file content for the agent-neo-prerun diff scheme.
     * uri.path is "/<repo-relative-path>", uri.query is the git ref.
     */
    private async providePreRunContent(uri: vscode.Uri): Promise<string> {
        try {
            const repo = await this._getGitRepo();
            const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!repo || !root || !uri.query) { return ''; }
            const relPath = uri.path.replace(/^\//, '');
            return await repo.show(uri.query, path.join(root, relPath));
        } catch {
            // file did not exist at the pre-run ref — empty left side
            return '';
        }
    }

    /**
     * Open a diff of an edited file against its pre-run content when a
     * pre-run git ref is known; fall back to opening the file normally.
     */
    private async _openDiff(relPath: string, ref?: string, oldPath?: string) {
        try {
            const folder = vscode.workspace.workspaceFolders?.[0];
            if (!folder || !relPath) { return; }
            const repo = await this._getGitRepo();
            if (ref && repo) {
                const fileUri = vscode.Uri.joinPath(folder.uri, relPath);
                // For renames, the left side is the old path's pre-run content
                const leftRel = oldPath || relPath;
                const leftUri = vscode.Uri.from({
                    scheme: 'agent-neo-prerun',
                    path: '/' + leftRel.replace(/\\/g, '/'),
                    query: ref,
                });
                const title = oldPath
                    ? oldPath + ' → ' + relPath + ' (Agent NEO rename)'
                    : relPath + ' (Agent NEO changes)';
                if (fs.existsSync(fileUri.fsPath)) {
                    await vscode.commands.executeCommand('vscode.diff', leftUri, fileUri, title);
                } else {
                    // file was deleted during the run — show the pre-run version
                    const doc = await vscode.workspace.openTextDocument(leftUri);
                    await vscode.window.showTextDocument(doc, { preview: true });
                }
                return;
            }
        } catch {
            // diff unavailable — fall back to a plain open
        }
        await this._revealFile(relPath);
    }

    /**
     * Resolve VS Code's built-in Git API (repository 0) — null when unavailable.
     */
    private async _getGitRepo(): Promise<any> {
        if (this.gitRepo) { return this.gitRepo; }
        try {
            const gitExt = vscode.extensions.getExtension<any>('vscode.git');
            if (!gitExt) { return null; }
            if (!gitExt.isActive) { await gitExt.activate(); }
            const api = gitExt.exports?.getAPI?.(1);
            const repo = api?.repositories?.[0] ?? null;
            if (repo) {
                this.gitRepo = repo;
                // Push fresh workspace info on git state changes (debounced)
                repo.state.onDidChange(() => {
                    if (this.workspaceInfoTimer) { clearTimeout(this.workspaceInfoTimer); }
                    this.workspaceInfoTimer = setTimeout(() => this.postWorkspaceInfo(), 500);
                }, undefined, this.context.subscriptions);
            }
            return repo;
        } catch {
            return null;
        }
    }

    /**
     * Gather workspace + git info and push it to the webview header strip.
     */
    private async initWorkspaceInfo() {
        await this._getGitRepo();
        this.postWorkspaceInfo();
    }

    private postWorkspaceInfo() {
        const folder = vscode.workspace.workspaceFolders?.[0];
        const info: any = {
            type: 'workspaceInfo',
            workspace: folder?.name ?? null,
            branch: null,
            dirty: null,
        };
        try {
            const repo = this.gitRepo;
            if (repo) {
                info.branch = repo.state.HEAD?.name ?? null;
                info.dirty =
                    (repo.state.workingTreeChanges?.length ?? 0) +
                    (repo.state.indexChanges?.length ?? 0);
            }
        } catch {
            // git info is best-effort — workspace name still shown
        }
        this.post(info);
    }

    /**
     * Fetch the configured model catalog from the backend and push it to the
     * webview's model picker. Best-effort — the picker keeps its fallback
     * options if the backend is unreachable.
     */
    private async sendModelList() {
        try {
            const data = await this.apiClient.getModels();
            this.post({
                type: 'modelList',
                models: data?.models ?? [],
                catalog: data?.catalog ?? [],
            });
        } catch {
            // best-effort — webview falls back to built-in options
        }
    }

    /**
     * Gather data for the in-webview settings surface.
     */
    private async handleGetSettingsInfo() {
        const config = vscode.workspace.getConfiguration('agentNeo');
        const folder = vscode.workspace.workspaceFolders?.[0];

        const guidelineFiles: string[] = [];
        if (folder) {
            for (const name of ['.neo', '.neo.md', 'AGENT.md']) {
                try {
                    const p = path.join(folder.uri.fsPath, name);
                    if (fs.existsSync(p) && fs.statSync(p).isFile()) {
                        guidelineFiles.push(name);
                    }
                } catch {
                    // unreadable entry — skip
                }
            }
        }

        const healthy = await this.apiClient.checkHealth();
        const repo = await this._getGitRepo();

        // Managed repos + token existence (value never leaves SecretStorage)
        let managedRepos: any[] = [];
        let activeRepoId: string | null = null;
        try {
            const data = await this.apiClient.listRepos();
            managedRepos = data?.repos ?? [];
            activeRepoId = data?.active_repo_id ?? null;
        } catch {
            // backend unreachable — Repos tab shows an empty state
        }
        const githubTokenSet = await this.storage.hasGitHubToken();

        // External integrations (best-effort; re-sync secrets into backend memory)
        let mcpServers: any[] = [];
        let cliTools: any[] = [];
        try {
            mcpServers = (await this.apiClient.listMcpServers())?.servers ?? [];
            cliTools = (await this.apiClient.listCliTools())?.tools ?? [];
            void this.integrations.syncMcpSecrets(mcpServers);
        } catch {
            // backend unreachable — Integrations tab shows an empty state
        }

        this.post({
            type: 'settingsInfo',
            apiUrl: config.get('apiUrl', 'http://127.0.0.1:8000'),
            tokenSet: !!config.get('apiToken', ''),
            healthy,
            guidelineFiles,
            workspace: folder?.name ?? null,
            workspacePath: folder?.uri.fsPath ?? null,
            branch: repo?.state?.HEAD?.name ?? null,
            dirty: repo
                ? (repo.state.workingTreeChanges?.length ?? 0) +
                  (repo.state.indexChanges?.length ?? 0)
                : null,
            managedRepos,
            activeRepoId,
            githubTokenSet,
            mcpServers,
            cliTools,
        });
    }

    /**
     * Clone a GitHub repo to a user-chosen folder, then open it in VS Code.
     */
    private async handleCloneRepo(url: string) {
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
        if (!picks || picks.length === 0) { return; }

        const destDir = picks[0].fsPath;
        const repoName = url.split('/').pop()?.replace(/\.git$/, '') || 'repo';
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const path = require('path') as typeof import('path');
        const clonePath = path.join(destDir, repoName);

        this.post({ type: 'userMessage', message: `/clone ${url}` });
        this.post({ type: 'loading', loading: true });

        const clonePromise = new Promise<void>((resolve, reject) => {
            // eslint-disable-next-line @typescript-eslint/no-var-requires
            const cp = require('child_process') as typeof import('child_process');
            cp.execFile('git', ['clone', url, clonePath], { timeout: 120_000 }, (err) => {
                if (err) { reject(err); } else { resolve(); }
            });
        });

        vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: `Cloning ${repoName}…`, cancellable: false },
            () => clonePromise
        );

        clonePromise.then(async () => {
            const folderUri = vscode.Uri.file(clonePath);
            // Open the cloned folder in the current window so the backend
            // picks up the new workspace_path on the next /run.
            await vscode.commands.executeCommand('vscode.openFolder', folderUri, { forceNewWindow: false });
        }).catch((err: Error) => {
            vscode.window.showErrorMessage(`Clone failed: ${err.message}`);
            this.post({ type: 'error', message: `Clone failed: ${err.message}` });
        }).finally(() => {
            this.post({ type: 'loading', loading: false });
        });
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

