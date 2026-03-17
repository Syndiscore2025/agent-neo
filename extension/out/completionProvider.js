"use strict";
/**
 * AGENT NEO - Completion Provider
 * Provides inline code completion suggestions.
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
exports.CompletionProvider = void 0;
const vscode = __importStar(require("vscode"));
const apiClient_1 = require("./apiClient");
class CompletionProvider {
    constructor() {
        this.apiClient = new apiClient_1.ApiClient();
    }
    /**
     * Provide inline completion items.
     */
    async provideInlineCompletionItems(document, position, context, token) {
        try {
            // Don't trigger on every keystroke - only when user pauses
            // This is handled by VS Code's debouncing, but we can add our own check
            // Get surrounding code context
            const surroundingCode = this.getSurroundingCode(document, position);
            // Get language
            const language = document.languageId;
            // Call API for completion
            const response = await this.apiClient.getCompletion(document.fileName, position.line, position.character, surroundingCode, language);
            // Return empty if no suggestion or low confidence
            if (!response.suggestion || response.confidence < 0.3) {
                return undefined;
            }
            // Create inline completion item
            const item = new vscode.InlineCompletionItem(response.suggestion, new vscode.Range(position, position));
            return [item];
        }
        catch (error) {
            console.error('Completion provider error:', error);
            return undefined;
        }
    }
    /**
     * Get surrounding code context for completion.
     */
    getSurroundingCode(document, position) {
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
    dispose() {
        // Cleanup if needed
    }
}
exports.CompletionProvider = CompletionProvider;
//# sourceMappingURL=completionProvider.js.map