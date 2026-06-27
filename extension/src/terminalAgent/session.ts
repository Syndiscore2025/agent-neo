/**
 * AGENT NEO - Terminal Agent Orchestrator: Session model
 *
 * One TerminalAgentSession per run. Pure data + small helpers; no `vscode`
 * import so it stays unit-testable. Secret redaction happens at the
 * persistence boundary (history.ts / Phase 5), never here.
 */

import { randomUUID } from 'crypto';
import { Milestone, DetectedError } from './providers/types';

export type SessionStatus =
    | 'idle'
    | 'prompt_review'
    | 'running'
    | 'observing'
    | 'paused'
    | 'completed'
    | 'failed'
    | 'cancelled';

export interface SessionSuggestion {
    id: string;
    title: string;
    /** Optional ready-to-send prompt the user can copy/send. */
    prompt?: string;
}

export interface SafetyFlag {
    rule: string;
    detail: string;
    severity: 'warn' | 'danger';
}

export interface TerminalAgentSession {
    session_id: string;
    provider_id: string;
    provider_name: string;
    repo_path: string;
    original_user_request: string;
    generated_prompt: string;
    edited_prompt: string;
    current_branch_at_start: string | null;
    current_branch_current: string | null;
    git_status_at_start: string | null;
    git_status_current: string | null;
    terminal_session_id: string | null;
    process_id: number | null;
    started_at: string;
    ended_at: string | null;
    status: SessionStatus;
    output_buffer: string;
    parsed_milestones: Milestone[];
    detected_errors: DetectedError[];
    detected_warnings: string[];
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

export interface CreateSessionInput {
    provider_id: string;
    provider_name: string;
    repo_path: string;
    original_user_request: string;
    generated_prompt: string;
    edited_prompt?: string;
    current_branch_at_start?: string | null;
    git_status_at_start?: string | null;
    status?: SessionStatus;
}

/** Build a fully-defaulted session from the minimal required inputs. */
export function createSession(input: CreateSessionInput): TerminalAgentSession {
    return {
        session_id: randomUUID(),
        provider_id: input.provider_id,
        provider_name: input.provider_name,
        repo_path: input.repo_path,
        original_user_request: input.original_user_request,
        generated_prompt: input.generated_prompt,
        edited_prompt: input.edited_prompt ?? input.generated_prompt,
        current_branch_at_start: input.current_branch_at_start ?? null,
        current_branch_current: input.current_branch_at_start ?? null,
        git_status_at_start: input.git_status_at_start ?? null,
        git_status_current: input.git_status_at_start ?? null,
        terminal_session_id: null,
        process_id: null,
        started_at: new Date().toISOString(),
        ended_at: null,
        status: input.status ?? 'prompt_review',
        output_buffer: '',
        parsed_milestones: [],
        detected_errors: [],
        detected_warnings: [],
        changed_files: [],
        staged_files: [],
        unstaged_files: [],
        commits_created: [],
        tests_detected: false,
        tests_passed: 0,
        tests_failed: 0,
        suggestions: [],
        final_summary: null,
        safety_flags: [],
    };
}

/** Append text to the rolling buffer, bounded to the most recent `maxChars`. */
export function appendOutput(
    session: TerminalAgentSession,
    chunk: string,
    maxChars = 200_000,
): void {
    session.output_buffer = (session.output_buffer + chunk).slice(-maxChars);
}

/** Mark a session finished with a terminal status + timestamp. */
export function endSession(
    session: TerminalAgentSession,
    status: Extract<SessionStatus, 'completed' | 'failed' | 'cancelled'>,
): void {
    session.status = status;
    session.ended_at = new Date().toISOString();
}

const TERMINAL_STATUSES: SessionStatus[] = ['completed', 'failed', 'cancelled'];

export function isTerminal(session: TerminalAgentSession): boolean {
    return TERMINAL_STATUSES.includes(session.status);
}
