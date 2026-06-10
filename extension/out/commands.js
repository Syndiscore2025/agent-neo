"use strict";
/**
 * AGENT NEO - Commands
 * Registers VS Code commands.
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
exports.registerCommands = registerCommands;
const vscode = __importStar(require("vscode"));
/**
 * Register all extension commands.
 */
function registerCommands(context, chatPanel, statusBar, storage, repoManager) {
    // Open Chat
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.openChat', () => {
        chatPanel.show();
    }));
    // Explain Selection
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.explainSelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected');
            return;
        }
        chatPanel.show();
        await chatPanel.sendMessage('Explain this code:\n\n' + selection);
    }));
    // Refactor Selection
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.refactorSelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected');
            return;
        }
        chatPanel.show();
        await chatPanel.sendMessage('Refactor this code to improve readability and maintainability:\n\n' + selection);
    }));
    // Generate Tests
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.generateTests', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected');
            return;
        }
        chatPanel.show();
        await chatPanel.sendMessage('Generate comprehensive unit tests for this code:\n\n' + selection);
    }));
    // Fix Selection
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.fixSelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected');
            return;
        }
        chatPanel.show();
        await chatPanel.sendMessage('Find and fix any bugs or issues in this code:\n\n' + selection);
    }));
    // Ask About Current File
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.askAboutFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor');
            return;
        }
        const fileName = vscode.workspace.asRelativePath(editor.document.uri);
        chatPanel.show();
        await chatPanel.sendMessage('Tell me about the file: ' + fileName);
    }));
    // Open dedicated Agent NEO terminal
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.openTerminal', () => {
        chatPanel.openTerminal();
    }));
    // Managed repos: list / attach local / clone GitHub / choose active
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.manageRepos', async () => {
        await repoManager.manageRepos();
    }));
    // Set/update the GitHub token (SecretStorage only — never plaintext)
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.setGitHubToken', async () => {
        const token = await vscode.window.showInputBox({
            prompt: 'GitHub personal access token (stored in VS Code SecretStorage)',
            password: true,
            ignoreFocusOut: true
        });
        if (token === undefined) {
            return;
        }
        if (!token.trim()) {
            vscode.window.showWarningMessage('Token unchanged (empty input). Use "Clear GitHub Token" to remove it.');
            return;
        }
        await storage.setGitHubToken(token.trim());
        vscode.window.showInformationMessage('GitHub token saved to SecretStorage.');
    }));
    // Clear the GitHub token
    context.subscriptions.push(vscode.commands.registerCommand('agent-neo.clearGitHubToken', async () => {
        await storage.clearGitHubToken();
        vscode.window.showInformationMessage('GitHub token cleared.');
    }));
}
//# sourceMappingURL=commands.js.map