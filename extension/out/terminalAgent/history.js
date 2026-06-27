"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Run history
 *
 * Persists a NON-SECRET summary of each session. The raw output_buffer is
 * never stored (it may contain secrets); only structured, redactable fields
 * are kept. Storage is a globalState-shaped key/value store, injected so this
 * stays unit-testable without `vscode`.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.SessionHistory = void 0;
exports.toSummary = toSummary;
const safetyDetector_1 = require("./safetyDetector");
const HISTORY_KEY = 'agentNeo.terminalAgent.history';
const DEFAULT_MAX_ENTRIES = 50;
/**
 * Project a full session down to its persistable, non-secret summary. The raw
 * output buffer is dropped entirely, and every free-text field (request,
 * prompts, summary, suggestion prompts) is run through `redactSecrets` so no
 * key/token can reach storage even if it appeared in a prompt or paste.
 */
function toSummary(session) {
    return {
        session_id: session.session_id,
        provider_id: session.provider_id,
        provider_name: session.provider_name,
        repo_path: session.repo_path,
        original_user_request: (0, safetyDetector_1.redactSecrets)(session.original_user_request),
        generated_prompt: (0, safetyDetector_1.redactSecrets)(session.generated_prompt),
        edited_prompt: (0, safetyDetector_1.redactSecrets)(session.edited_prompt),
        current_branch_at_start: session.current_branch_at_start,
        current_branch_current: session.current_branch_current,
        status: session.status,
        started_at: session.started_at,
        ended_at: session.ended_at,
        changed_files: [...session.changed_files],
        staged_files: [...session.staged_files],
        unstaged_files: [...session.unstaged_files],
        commits_created: [...session.commits_created],
        tests_detected: session.tests_detected,
        tests_passed: session.tests_passed,
        tests_failed: session.tests_failed,
        suggestions: session.suggestions.map(s => ({
            ...s,
            title: (0, safetyDetector_1.redactSecrets)(s.title),
            prompt: s.prompt ? (0, safetyDetector_1.redactSecrets)(s.prompt) : s.prompt,
        })),
        final_summary: session.final_summary ? (0, safetyDetector_1.redactSecrets)(session.final_summary) : null,
        safety_flags: (0, safetyDetector_1.redactSafetyFlags)(session.safety_flags),
    };
}
class SessionHistory {
    constructor(store, maxEntries = DEFAULT_MAX_ENTRIES) {
        this.store = store;
        this.maxEntries = maxEntries;
    }
    /** Most-recent-first list of stored summaries. */
    list() {
        const raw = this.store.get(HISTORY_KEY);
        return Array.isArray(raw) ? raw : [];
    }
    get(sessionId) {
        return this.list().find(s => s.session_id === sessionId);
    }
    /**
     * Upsert a session's summary (newest first), bounded to maxEntries.
     * Re-saving the same session_id updates the existing entry in place.
     */
    async save(session) {
        const summary = toSummary(session);
        const rest = this.list().filter(s => s.session_id !== summary.session_id);
        const updated = [summary, ...rest].slice(0, this.maxEntries);
        await this.store.update(HISTORY_KEY, updated);
        return summary;
    }
    async clear() {
        await this.store.update(HISTORY_KEY, []);
    }
}
exports.SessionHistory = SessionHistory;
//# sourceMappingURL=history.js.map