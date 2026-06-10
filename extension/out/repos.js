"use strict";
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
exports.RepoManager = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
class RepoManager {
    constructor(apiClient, storage) {
        this.apiClient = apiClient;
        this.storage = storage;
    }
    /** Main entry: list repos + add/clone actions in one quick pick. */
    async manageRepos() {
        let repos = [];
        let activeId;
        try {
            const data = await this.apiClient.listRepos();
            repos = data?.repos ?? [];
            activeId = data?.active_repo_id ?? undefined;
        }
        catch {
            vscode.window.showWarningMessage('Agent NEO backend unreachable — showing actions only.');
        }
        const items = repos.map((r) => ({
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
        items.push({ action: 'attach', label: '$(add) Add local repo…', description: 'Register an existing git repo on disk' }, { action: 'clone', label: '$(repo-clone) Clone GitHub repo…', description: 'Clone into a folder you choose' });
        const pick = await vscode.window.showQuickPick(items, {
            placeHolder: 'Agent NEO managed repos — select to activate',
            matchOnDescription: true
        });
        if (!pick) {
            return;
        }
        if (pick.action === 'attach') {
            await this.attachLocalRepo();
        }
        else if (pick.action === 'clone') {
            await this.cloneGitHubRepo();
        }
        else if (pick.repo) {
            await this.activateRepo(pick.repo);
        }
    }
    /** Attach an already-local git repo chosen via folder dialog. */
    async attachLocalRepo() {
        const picks = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Attach this repo'
        });
        if (!picks || picks.length === 0) {
            return;
        }
        try {
            const repo = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Attaching and indexing repo…' }, () => this.apiClient.attachRepo(picks[0].fsPath));
            await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });
            vscode.window.showInformationMessage('Attached ' + repo.name + '.');
            await this.activateRepo(repo);
        }
        catch (err) {
            vscode.window.showErrorMessage('Attach failed: ' + (err?.response?.data?.detail || err.message));
        }
    }
    /** Clone a GitHub repo into a user-chosen folder, then register it. */
    async cloneGitHubRepo() {
        const url = await vscode.window.showInputBox({
            prompt: 'GitHub repository URL (https)',
            placeHolder: 'https://github.com/owner/repo',
            ignoreFocusOut: true
        });
        if (!url) {
            return;
        }
        const picks = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Clone into this folder'
        });
        if (!picks || picks.length === 0) {
            return;
        }
        const repoName = url.split('/').pop()?.replace(/\.git$/, '') || 'repo';
        const destPath = path.join(picks[0].fsPath, repoName);
        const token = await this.storage.getGitHubToken();
        try {
            const repo = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Cloning ' + repoName + '…' }, () => this.apiClient.cloneRepo(url, destPath, undefined, token));
            await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });
            const note = repo.attached_existing ? ' (already present — attached)' : '';
            vscode.window.showInformationMessage('Cloned ' + repo.name + note + '.');
            await this.activateRepo(repo);
        }
        catch (err) {
            vscode.window.showErrorMessage('Clone failed: ' + (err?.response?.data?.detail || err.message));
        }
    }
    /** Activate a repo (backend + globalState) and offer to open its folder. */
    async activateRepo(repo) {
        try {
            await this.apiClient.activateRepo(repo.id);
        }
        catch {
            // backend activation is best-effort; local selection still applies
        }
        await this.storage.setActiveRepoId(repo.id);
        await this.storage.addRecentRepo({ id: repo.id, name: repo.name, path: repo.path });
        const current = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (current && path.resolve(current) === path.resolve(repo.path)) {
            return;
        }
        const open = await vscode.window.showInformationMessage(repo.name + ' is now the active repo. Open its folder so runs target it?', 'Open Folder', 'Not Now');
        if (open === 'Open Folder') {
            await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(repo.path), { forceNewWindow: false });
        }
    }
}
exports.RepoManager = RepoManager;
//# sourceMappingURL=repos.js.map