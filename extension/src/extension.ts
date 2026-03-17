/**
 * AGENT NEO - VS Code Extension
 * Main extension entry point.
 */

import * as vscode from 'vscode';
import { ChatPanel } from './chatPanel';
import { CompletionProvider } from './completionProvider';
import { registerCommands } from './commands';
import { StatusBarManager } from './statusBar';

let chatPanel: ChatPanel | undefined;
let completionProvider: CompletionProvider | undefined;
let statusBar: StatusBarManager | undefined;

/**
 * Extension activation.
 */
export function activate(context: vscode.ExtensionContext) {
    console.log('Agent NEO extension activating...');

    // Initialize status bar
    statusBar = new StatusBarManager();
    context.subscriptions.push(statusBar);

    // Initialize chat panel
    chatPanel = new ChatPanel(context);

    // Initialize completion provider
    const config = vscode.workspace.getConfiguration('agentNeo');
    if (config.get('enableInlineCompletion', true)) {
        completionProvider = new CompletionProvider();

        // Register inline completion provider for all languages
        const provider = vscode.languages.registerInlineCompletionItemProvider(
            { pattern: '**' },  // All files
            completionProvider
        );

        context.subscriptions.push(provider);
        console.log('Agent NEO inline completion provider registered');
    }

    // Register commands
    registerCommands(context, chatPanel, statusBar);

    console.log('Agent NEO extension activated');
}

/**
 * Extension deactivation.
 */
export function deactivate() {
    console.log('Agent NEO extension deactivating...');
    
    if (chatPanel) {
        chatPanel.dispose();
    }
    
    if (completionProvider) {
        completionProvider.dispose();
    }
}

