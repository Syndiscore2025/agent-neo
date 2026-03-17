/**
 * AGENT NEO - Completion Provider
 * Provides inline code completion suggestions.
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';

export class CompletionProvider implements vscode.InlineCompletionItemProvider {
    private apiClient: ApiClient;

    constructor() {
        this.apiClient = new ApiClient();
    }

    /**
     * Provide inline completion items.
     */
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionItem[] | vscode.InlineCompletionList | undefined> {
        try {
            // Don't trigger on every keystroke - only when user pauses
            // This is handled by VS Code's debouncing, but we can add our own check

            // Get surrounding code context
            const surroundingCode = this.getSurroundingCode(document, position);

            // Get language
            const language = document.languageId;

            // Call API for completion
            const response = await this.apiClient.getCompletion(
                document.fileName,
                position.line,
                position.character,
                surroundingCode,
                language
            );

            // Return empty if no suggestion or low confidence
            if (!response.suggestion || response.confidence < 0.3) {
                return undefined;
            }

            // Create inline completion item
            const item = new vscode.InlineCompletionItem(
                response.suggestion,
                new vscode.Range(position, position)
            );

            return [item];

        } catch (error) {
            console.error('Completion provider error:', error);
            return undefined;
        }
    }

    /**
     * Get surrounding code context for completion.
     */
    private getSurroundingCode(document: vscode.TextDocument, position: vscode.Position): string {
        // Get 10 lines before and 5 lines after cursor
        const linesBefore = 10;
        const linesAfter = 5;

        const startLine = Math.max(0, position.line - linesBefore);
        const endLine = Math.min(document.lineCount - 1, position.line + linesAfter);

        let code = '';

        // Add lines before cursor
        for (let i = startLine; i < position.line; i++) {
            code += document.lineAt(i).text + '\n';
        }

        // Add current line up to cursor
        const currentLine = document.lineAt(position.line).text;
        code += currentLine.substring(0, position.character);
        code += '<CURSOR>';
        code += currentLine.substring(position.character);
        code += '\n';

        // Add lines after cursor
        for (let i = position.line + 1; i <= endLine; i++) {
            code += document.lineAt(i).text + '\n';
        }

        return code;
    }

    /**
     * Dispose the provider.
     */
    public dispose() {
        // Cleanup if needed
    }
}

