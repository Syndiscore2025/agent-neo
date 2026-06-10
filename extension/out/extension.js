"use strict";
/**
 * AGENT NEO - VS Code Extension
 * Main extension entry point.
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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const chatPanel_1 = require("./chatPanel");
const completionProvider_1 = require("./completionProvider");
const commands_1 = require("./commands");
const statusBar_1 = require("./statusBar");
const storage_1 = require("./storage");
const repos_1 = require("./repos");
const integrations_1 = require("./integrations");
const apiClient_1 = require("./apiClient");
let chatPanel;
let completionProvider;
let statusBar;
/**
 * Extension activation.
 */
function activate(context) {
    console.log('Agent NEO extension activating...');
    // Initialize status bar
    statusBar = new statusBar_1.StatusBarManager();
    context.subscriptions.push(statusBar);
    // Initialize chat panel + sidebar view
    chatPanel = new chatPanel_1.ChatPanel(context);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(chatPanel_1.ChatPanel.viewId, chatPanel, {
        webviewOptions: { retainContextWhenHidden: true }
    }));
    // Initialize completion provider
    const config = vscode.workspace.getConfiguration('agentNeo');
    if (config.get('enableInlineCompletion', true)) {
        completionProvider = new completionProvider_1.CompletionProvider();
        // Register inline completion provider for all languages
        const provider = vscode.languages.registerInlineCompletionItemProvider({ pattern: '**' }, // All files
        completionProvider);
        context.subscriptions.push(provider);
        console.log('Agent NEO inline completion provider registered');
    }
    // Storage split (globalState + SecretStorage) and managed repo flows
    const storage = new storage_1.NeoStorage(context);
    const apiClient = new apiClient_1.ApiClient();
    const repoManager = new repos_1.RepoManager(apiClient, storage);
    const integrationsManager = new integrations_1.IntegrationsManager(apiClient, storage);
    // Register commands
    (0, commands_1.registerCommands)(context, chatPanel, statusBar, storage, repoManager, integrationsManager);
    console.log('Agent NEO extension activated');
}
/**
 * Extension deactivation.
 */
function deactivate() {
    console.log('Agent NEO extension deactivating...');
    if (chatPanel) {
        chatPanel.dispose();
    }
    if (completionProvider) {
        completionProvider.dispose();
    }
}
//# sourceMappingURL=extension.js.map