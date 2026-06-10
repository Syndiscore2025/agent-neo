"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.NeoStorage = void 0;
const KEY_ACTIVE_REPO = 'agentNeo.activeRepoId';
const KEY_RECENT_REPOS = 'agentNeo.recentRepos';
const SECRET_GITHUB = 'agentNeo.secret.github';
const MAX_RECENT_REPOS = 10;
class NeoStorage {
    constructor(context) {
        this.context = context;
    }
    // ── globalState: UI/session state ───────────────────────────────────
    getActiveRepoId() {
        return this.context.globalState.get(KEY_ACTIVE_REPO) || undefined;
    }
    async setActiveRepoId(id) {
        await this.context.globalState.update(KEY_ACTIVE_REPO, id);
    }
    getRecentRepos() {
        const stored = this.context.globalState.get(KEY_RECENT_REPOS);
        return Array.isArray(stored) ? stored : [];
    }
    async addRecentRepo(repo) {
        const rest = this.getRecentRepos().filter(r => r.id !== repo.id);
        const updated = [repo, ...rest].slice(0, MAX_RECENT_REPOS);
        await this.context.globalState.update(KEY_RECENT_REPOS, updated);
    }
    // ── SecretStorage: tokens only ───────────────────────────────────────
    async getGitHubToken() {
        return this.context.secrets.get(SECRET_GITHUB);
    }
    async setGitHubToken(token) {
        await this.context.secrets.store(SECRET_GITHUB, token);
    }
    async clearGitHubToken() {
        await this.context.secrets.delete(SECRET_GITHUB);
    }
    async hasGitHubToken() {
        return !!(await this.getGitHubToken());
    }
    /** Generic secret accessors for future integrations (MCP, CLIs, …). */
    async getSecret(name) {
        return this.context.secrets.get('agentNeo.secret.' + name);
    }
    async setSecret(name, value) {
        await this.context.secrets.store('agentNeo.secret.' + name, value);
    }
    async clearSecret(name) {
        await this.context.secrets.delete('agentNeo.secret.' + name);
    }
}
exports.NeoStorage = NeoStorage;
//# sourceMappingURL=storage.js.map