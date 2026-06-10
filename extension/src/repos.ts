/**
 * AGENT NEO - Managed Repos
 *
 * UI flows for the backend's managed repo registry:
 *   - list managed repos with metadata
 *   - attach an already-local git repo
 *   - clone a GitHub repo into a user-chosen path (explicit, never silent)
 *   - choose the active repo
 *
 * Tokens come from SecretStorage only and travel only in the clone request.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { ApiClient } from './apiClient';
import { NeoStorage } from './storage';

interface RepoPick extends vscode.QuickPickItem {
    action: 'select' | 'attach' | 'clone';
    repo?: any;
}

export class RepoManager {
    constructor(
        private readonly apiClient: ApiClient,
        private readonly storage: NeoStorage
    ) {}

    /** Main entry: list repos + add/clone actions in one quick pick. */
    async manageRepos(): Promise<void> {
        let repos: any[] = [];
        let activeId: string | undefined;
        try {
            const data = await this.apiClient.listRepos();
            repos = data?.repos ?? [];
            activeId = data?.active_repo_id ?? undefined;
        } catch {
            vscode.window.showWarningMessage('Agent NEO backend unreachable — showing actions only.');
        }

        const items: RepoPick[] = repos.map((r: any) => ({
            action: 'select',
            repo: r,
            label: (r.id === activeId ? '$(check) ' : '$(repo) ') + r.name,
            description: r.path,
            detail: [
                r.default_branch ? 'branch: ' + r.default_branch : null,
                r.remote_url ? 'remote: ' + r.remote_url : 'no remote',
                r.last_indexed_at ? 'indexed: ' + r.last_indexed_at.slice(0, 19).replace('T', ' ') : 'not indexed'
            ].filter(Boolean).join('  ·  ')
        }));
        items.push(
            { action: 'attach', label: '$(add) Add local repo…', description: 'Register an existing git repo on disk' },
            { action: 'clone', label: '$(repo-clone) Clone GitHub repo…', description: 'Clone into a folder you choose' }
        );

        const pick = await vscode.window.showQuickPick(items, {
            placeHolder: 'Agent NEO managed repos — select to activate',
            matchOnDescription: true
        });
        if (!pick) { return; }

        if (pick.action === 'attach') { await this.attachLocalRepo(); }
        else if (pick.action === 'clone') { await this.cloneGitHubRepo(); }
        else if (pick.repo) { await this.activateRepo(pick.repo); }
    }

    /** Attach an already-local git repo chosen via folder dialog. */
    async attachLocalRepo(): Promise<void> {
        const picks = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Attach this repo'
        });
        if (!picks || picks.length === 0) { return; }

        try {
            const repo = await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Attaching and indexing repo…' },
                () => this.apiClient.attachRepo(picks[0].fsPath)
            );
            await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });
            vscode.window.showInformationMessage('Attached ' + repo.name + '.');
            await this.activateRepo(repo);
        } catch (err: any) {
            vscode.window.showErrorMessage('Attach failed: ' + (err?.response?.data?.detail || err.message));
        }
    }

    /** Clone a GitHub repo into a user-chosen folder, then register it. */
    async cloneGitHubRepo(): Promise<void> {
        const url = await vscode.window.showInputBox({
            prompt: 'GitHub repository URL (https)',
            placeHolder: 'https://github.com/owner/repo',
            ignoreFocusOut: true
        });
        if (!url) { return; }

        const picks = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Clone into this folder'
        });
        if (!picks || picks.length === 0) { return; }

        const repoName = url.split('/').pop()?.replace(/\.git$/, '') || 'repo';
        const destPath = path.join(picks[0].fsPath, repoName);
        const token = await this.storage.getGitHubToken();

        try {
            const repo = await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Cloning ' + repoName + '…' },
                () => this.apiClient.cloneRepo(url, destPath, undefined, token)
            );
            await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });
            const note = repo.attached_existing ? ' (already present — attached)' : '';
            vscode.window.showInformationMessage('Cloned ' + repo.name + note + '.');
            await this.activateRepo(repo);
        } catch (err: any) {
            vscode.window.showErrorMessage('Clone failed: ' + (err?.response?.data?.detail || err.message));
        }
    }

    /** Activate a repo (backend + globalState) and offer to open its folder. */
    private async activateRepo(repo: any): Promise<void> {
        try {
            await this.apiClient.activateRepo(repo.id);
        } catch {
            // backend activation is best-effort; local selection still applies
        }
        await this.storage.setActiveRepoId(repo.id);
        await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });

        const current = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (current && path.resolve(current) === path.resolve(repo.path)) { return; }

        const open = await vscode.window.showInformationMessage(
            repo.name + ' is now the active repo. Open its folder so runs target it?',
            'Open Folder', 'Not Now'
        );
        if (open === 'Open Folder') {
            await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(repo.path), { forceNewWindow: false });
        }
    }
}
