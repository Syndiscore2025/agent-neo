/**
 * AGENT NEO - Commands
 * Registers VS Code commands.
 */

import * as vscode from 'vscode';
import { ChatPanel } from './chatPanel';
import { StatusBarManager } from './statusBar';

/**
 * Register all extension commands.
 */
export function registerCommands(
    context: vscode.ExtensionContext,
    chatPanel: ChatPanel,
    statusBar: StatusBarManager
) {
    // Open Chat
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.openChat', () => {
            chatPanel.show();
        })
    );

    // Explain Selection
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.explainSelection', async () => {
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
        })
    );

    // Refactor Selection
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.refactorSelection', async () => {
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
        })
    );

    // Generate Tests
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.generateTests', async () => {
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
        })
    );

    // Fix Selection
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.fixSelection', async () => {
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
        })
    );

    // Ask About Current File
    context.subscriptions.push(
        vscode.commands.registerCommand('agent-neo.askAboutFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }

            const fileName = vscode.workspace.asRelativePath(editor.document.uri);
            chatPanel.show();
            await chatPanel.sendMessage('Tell me about the file: ' + fileName);
        })
    );
}

