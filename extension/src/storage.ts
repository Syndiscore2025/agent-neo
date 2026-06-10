/**
 * AGENT NEO - Storage
 *
 * Single owner of the extension's persistence split:
 *   - globalState   → lightweight UI/session state (active repo id, recent
 *                     repos, preferences). Never large blobs.
 *   - SecretStorage → tokens only (GitHub + future integrations).
 *                     Never plaintext, never in settings.json.
 *
 * Durable data (repo registry, run history, repo index) lives on the
 * backend's local disk — this class never duplicates it.
 */

import * as vscode from 'vscode';

export interface RecentRepo {
    id: string;
    name: string;
    path: string;
}

const KEY_ACTIVE_REPO = 'agentNeo.activeRepoId';
const KEY_RECENT_REPOS = 'agentNeo.recentRepos';
const SECRET_GITHUB = 'agentNeo.secret.github';
const MAX_RECENT_REPOS = 10;

export class NeoStorage {
    constructor(private readonly context: vscode.ExtensionContext) {}

    // ── globalState: UI/session state ───────────────────────────────────

    getActiveRepoId(): string | undefined {
        return this.context.globalState.get<string>(KEY_ACTIVE_REPO) || undefined;
    }

    async setActiveRepoId(id: string | undefined): Promise<void> {
        await this.context.globalState.update(KEY_ACTIVE_REPO, id);
    }

    getRecentRepos(): RecentRepo[] {
        const stored = this.context.globalState.get<RecentRepo[]>(KEY_RECENT_REPOS);
        return Array.isArray(stored) ? stored : [];
    }

    async addRecentRepo(repo: RecentRepo): Promise<void> {
        const rest = this.getRecentRepos().filter(r => r.id !== repo.id);
        const updated = [repo, ...rest].slice(0, MAX_RECENT_REPOS);
        await this.context.globalState.update(KEY_RECENT_REPOS, updated);
    }

    // ── SecretStorage: tokens only ───────────────────────────────────────

    async getGitHubToken(): Promise<string | undefined> {
        return this.context.secrets.get(SECRET_GITHUB);
    }

    async setGitHubToken(token: string): Promise<void> {
        await this.context.secrets.store(SECRET_GITHUB, token);
    }

    async clearGitHubToken(): Promise<void> {
        await this.context.secrets.delete(SECRET_GITHUB);
    }

    async hasGitHubToken(): Promise<boolean> {
        return !!(await this.getGitHubToken());
    }

    /** Generic secret accessors for future integrations (MCP, CLIs, …). */
    async getSecret(name: string): Promise<string | undefined> {
        return this.context.secrets.get('agentNeo.secret.' + name);
    }

    async setSecret(name: string, value: string): Promise<void> {
        await this.context.secrets.store('agentNeo.secret.' + name, value);
    }

    async clearSecret(name: string): Promise<void> {
        await this.context.secrets.delete('agentNeo.secret.' + name);
    }
}
