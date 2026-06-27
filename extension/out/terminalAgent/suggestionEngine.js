"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Suggestion engine
 *
 * Turns a finished run's structured analysis into a short, prioritised list of
 * actionable next steps (each with an optional ready-to-send follow-up prompt).
 * Pure — no `vscode`. Suggestion prompts intentionally reference the task and
 * counts, never raw output, so no secret can leak through a suggestion.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildSuggestions = buildSuggestions;
const MAX_SUGGESTIONS = 8;
/** Build up to 8 prioritised suggestions from a run analysis. */
function buildSuggestions(input) {
    const { parsed, verification, changedFiles, safetyFlags } = input;
    const out = [];
    const add = (id, title, prompt) => out.push({ id, title, prompt });
    if (safetyFlags.some(f => f.severity === 'danger')) {
        add('safety', 'Review flagged risky command(s) before continuing — nothing was auto-run.');
    }
    if (parsed.errors.length) {
        add('fix-errors', `Investigate ${parsed.errors.length} error(s) reported by the agent`, `The previous run reported ${parsed.errors.length} error(s). Diagnose the root cause and fix them; re-run the relevant checks to confirm.`);
    }
    if (parsed.tests.failed > 0) {
        add('fix-tests', `Fix ${parsed.tests.failed} failing test(s)`, `${parsed.tests.failed} test(s) are failing after the last run. Make them pass without weakening assertions, then re-run the suite.`);
    }
    if (verification.unverifiedClaims.length) {
        add('unverified', `Verify ${verification.unverifiedClaims.length} claimed change(s) that did not alter any file`, `The agent claimed to change ${verification.unverifiedClaims.join(', ')}, but those files are unchanged on disk. Re-check whether the edits were actually applied.`);
    }
    if (verification.unclaimedChanges.length) {
        add('unclaimed', `Review ${verification.unclaimedChanges.length} unexpected change(s) the agent did not mention`, `These files changed without being mentioned: ${verification.unclaimedChanges.join(', ')}. Confirm each change is intended.`);
    }
    if (!parsed.tests.detected && changedFiles.length) {
        add('add-tests', 'Add tests for the changed files (none were detected this run)', `Add focused tests covering the behaviour changed in: ${changedFiles.slice(0, 10).join(', ')}.`);
    }
    if (changedFiles.length && input.commitsCreated.length === 0) {
        add('review-diff', `Review ${changedFiles.length} changed file(s) in Source Control — nothing was committed`);
    }
    if (input.commitsCreated.length) {
        add('verify-commit', `Confirm the ${input.commitsCreated.length} new commit(s) are correct before pushing`);
    }
    if (input.branchChanged) {
        add('branch-changed', 'The working branch changed during the run — verify you are on the intended branch');
    }
    if (input.status === 'completed' && parsed.tests.failed === 0 && !parsed.errors.length) {
        add('run-suite', 'Run the full test suite to confirm nothing regressed', 'Run the project\'s full test suite and report any failures.');
    }
    if (!out.length) {
        add('next-step', 'Describe the next change you want the terminal agent to make');
    }
    return out.slice(0, MAX_SUGGESTIONS);
}
//# sourceMappingURL=suggestionEngine.js.map