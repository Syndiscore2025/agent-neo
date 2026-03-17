/**
 * AGENT NEO - Status Bar Manager
 * Manages status bar display.
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';

export class StatusBarManager {
    private statusBarItem: vscode.StatusBarItem;
    private apiClient: ApiClient;
    private healthCheckInterval: NodeJS.Timeout | undefined;

    constructor() {
        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Right,
            100
        );
        this.apiClient = new ApiClient();
        
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
    private startHealthCheck() {
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
    private async checkHealth() {
        try {
            const isHealthy = await this.apiClient.checkHealth();
            
            if (isHealthy) {
                this.statusBarItem.text = '$(robot) Agent NEO';
                this.statusBarItem.tooltip = 'Agent NEO - Connected';
                this.statusBarItem.backgroundColor = undefined;
            } else {
                this.statusBarItem.text = '$(robot) Agent NEO $(warning)';
                this.statusBarItem.tooltip = 'Agent NEO - Connection failed';
                this.statusBarItem.backgroundColor = new vscode.ThemeColor(
                    'statusBarItem.warningBackground'
                );
            }
        } catch (error) {
            this.statusBarItem.text = '$(robot) Agent NEO $(error)';
            this.statusBarItem.tooltip = 'Agent NEO - Disconnected';
            this.statusBarItem.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.errorBackground'
            );
        }
    }

    /**
     * Update status with custom message.
     */
    public updateStatus(message: string, icon?: string) {
        const iconStr = icon ? `$(${icon}) ` : '';
        this.statusBarItem.text = `${iconStr}Agent NEO: ${message}`;
    }

    /**
     * Dispose the status bar item.
     */
    public dispose() {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
        }
        this.statusBarItem.dispose();
    }
}

