"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Session model
 *
 * One TerminalAgentSession per run. Pure data + small helpers; no `vscode`
 * import so it stays unit-testable. Secret redaction happens at the
 * persistence boundary (history.ts / Phase 5), never here.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createSession = createSession;
exports.appendOutput = appendOutput;
exports.endSession = endSession;
exports.isTerminal = isTerminal;
const crypto_1 = require("crypto");
/** Build a fully-defaulted session from the minimal required inputs. */
function createSession(input) {
    return {
        session_id: (0, crypto_1.randomUUID)(),
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
function appendOutput(session, chunk, maxChars = 200000) {
    session.output_buffer = (session.output_buffer + chunk).slice(-maxChars);
}
/** Mark a session finished with a terminal status + timestamp. */
function endSession(session, status) {
    session.status = status;
    session.ended_at = new Date().toISOString();
}
const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled'];
function isTerminal(session) {
    return TERMINAL_STATUSES.includes(session.status);
}
//# sourceMappingURL=session.js.map