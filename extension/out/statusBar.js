"use strict";
/**
 * AGENT NEO - Status Bar Manager
 * Manages status bar display.
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
exports.StatusBarManager = void 0;
const vscode = __importStar(require("vscode"));
const apiClient_1 = require("./apiClient");
class StatusBarManager {
    constructor() {
        this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        this.apiClient = new apiClient_1.ApiClient();
        this.statusBarItem.text = '$(robot) Agent NEO';
        this.statusBarItem.tooltip = 'Agent NEO - Checking connection...';
        this.statusBarItem.command = 'agent-neo.openChat';
        this.statusBarItem.show();
        // Start health check
        this.startHealthCheck();
    }
    /**
     * Start periodic health check.
     */
    startHealthCheck() {
        // Initial check
        this.checkHealth();
        // Check every 30 seconds
        this.healthCheckInterval = setInterval(() => {
            this.checkHealth();
        }, 30000);
    }
    /**
     * Check API health and update status.
     */
    async checkHealth() {
        try {
            const isHealthy = await this.apiClient.checkHealth();
            if (isHealthy) {
                this.statusBarItem.text = '$(robot) Agent NEO';
                this.statusBarItem.tooltip = 'Agent NEO - Connected';
                this.statusBarItem.backgroundColor = undefined;
            }
            else {
                this.statusBarItem.text = '$(robot) Agent NEO $(warning)';
                this.statusBarItem.tooltip = 'Agent NEO - Connection failed';
                this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
            }
        }
        catch (error) {
            this.statusBarItem.text = '$(robot) Agent NEO $(error)';
            this.statusBarItem.tooltip = 'Agent NEO - Disconnected';
            this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
        }
    }
    /**
     * Update status with custom message.
     */
    updateStatus(message, icon) {
        const iconStr = icon ? `$(${icon}) ` : '';
        this.statusBarItem.text = `${iconStr}Agent NEO: ${message}`;
    }
    /**
     * Dispose the status bar item.
     */
    dispose() {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        this.statusBarItem.dispose();
    }
}
exports.StatusBarManager = StatusBarManager;
//# sourceMappingURL=statusBar.js.map