/**
 * AGENT NEO - Terminal Agent Orchestrator: Run history
 *
 * Persists a NON-SECRET summary of each session. The raw output_buffer is
 * never stored (it may contain secrets); only structured, redactable fields
 * are kept. Storage is a globalState-shaped key/value store, injected so this
 * stays unit-testable without `vscode`.
 */

import {
    TerminalAgentSession,
    SessionStatus,
    SafetyFlag,
    SessionSuggestion,
} from './session';
import { redactSecrets, redactSafetyFlags } from './safetyDetector';

/** Matches the subset of vscode.Memento (globalState) we rely on. */
export interface KeyValueStore {
    get<T>(key: string): T | undefined;
    update(key: string, value: unknown): Thenable<void> | Promise<void>;
}

const HISTORY_KEY = 'agentNeo.terminalAgent.history';
const DEFAULT_MAX_ENTRIES = 50;

/** What we actually persist — deliberately excludes the raw output buffer. */
export interface SessionSummary {
    session_id: string;
    provider_id: string;
    provider_name: string;
    repo_path: string;
    original_user_request: string;
    generated_prompt: string;
    edited_prompt: string;
    current_branch_at_start: string | null;
    current_branch_current: string | null;
    status: SessionStatus;
    started_at: string;
    ended_at: string | null;
    changed_files: string[];
    staged_files: string[];
    unstaged_files: string[];
    commits_created: string[];
    tests_detected: boolean;
    tests_passed: number;
    tests_failed: number;
    suggestions: SessionSuggestion[];
    final_summary: string | null;
    safety_flags: SafetyFlag[];
}

/**
 * Project a full session down to its persistable, non-secret summary. The raw
 * output buffer is dropped entirely, and every free-text field (request,
 * prompts, summary, suggestion prompts) is run through `redactSecrets` so no
 * key/token can reach storage even if it appeared in a prompt or paste.
 */
export function toSummary(session: TerminalAgentSession): SessionSummary {
    return {
        session_id: session.session_id,
        provider_id: session.provider_id,
        provider_name: session.provider_name,
        repo_path: session.repo_path,
        original_user_request: redactSecrets(session.original_user_request),
        generated_prompt: redactSecrets(session.generated_prompt),
        edited_prompt: redactSecrets(session.edited_prompt),
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
            title: redactSecrets(s.title),
            prompt: s.prompt ? redactSecrets(s.prompt) : s.prompt,
        })),
        final_summary: session.final_summary ? redactSecrets(session.final_summary) : null,
        safety_flags: redactSafetyFlags(session.safety_flags),
    };
}

export class SessionHistory {
    constructor(
        private readonly store: KeyValueStore,
        private readonly maxEntries: number = DEFAULT_MAX_ENTRIES,
    ) {}

    /** Most-recent-first list of stored summaries. */
    list(): SessionSummary[] {
        const raw = this.store.get<SessionSummary[]>(HISTORY_KEY);
        return Array.isArray(raw) ? raw : [];
    }

    get(sessionId: string): SessionSummary | undefined {
        return this.list().find(s => s.session_id === sessionId);
    }

    /**
     * Upsert a session's summary (newest first), bounded to maxEntries.
     * Re-saving the same session_id updates the existing entry in place.
     */
    async save(session: TerminalAgentSession): Promise<SessionSummary> {
        const summary = toSummary(session);
        const rest = this.list().filter(s => s.session_id !== summary.session_id);
        const updated = [summary, ...rest].slice(0, this.maxEntries);
        await this.store.update(HISTORY_KEY, updated);
        return summary;
    }

    async clear(): Promise<void> {
        await this.store.update(HISTORY_KEY, []);
    }
}
