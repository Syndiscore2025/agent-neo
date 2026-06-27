/**
 * AGENT NEO - Terminal Agent Orchestrator: Prompt builder
 *
 * Turns a rough user request + repo/editor context into a structured CLI
 * prompt via {{variable}} substitution against a configurable template.
 *
 * Omission rule: if a variable is unavailable, its placeholder is removed
 * cleanly — never rendered as "null"/"undefined". Omission is block-level: a
 * blank-line-separated block that, after substitution, is empty or only label
 * lines (ending in ":") is dropped entirely, so dangling headers never remain.
 *
 * No `vscode` import — pure, unit-testable.
 */

export type PromptVarValue = string | string[] | undefined | null;
export interface PromptVariables {
    [name: string]: PromptVarValue;
}

/** Ships with the extension; overridable via settings. */
export const DEFAULT_PROMPT_TEMPLATE = [
    'Repository: {{repo_path}}',
    'Branch: {{current_branch}}',
    'Provider: {{provider_name}}',
    'Date: {{date_time}}',
    '',
    'Project memory:',
    '{{project_memory}}',
    '',
    'Open files:',
    '{{open_files}}',
    '',
    'Git status:',
    '{{git_status}}',
    '',
    'Changed files:',
    '{{changed_files}}',
    '',
    'Recent commits:',
    '{{recent_commits}}',
    '',
    'Task:',
    '{{user_request}}',
    '',
    'Instructions:',
    'Read the repository first. Understand the architecture. Implement only the ' +
        'requested task. Preserve existing behavior. Do not refactor unrelated code. ' +
        'Do not merge. Do not deploy. Do not force-push. Run relevant tests. Commit ' +
        "changes only if explicitly requested or if this project's workflow requires " +
        'it. At the end, summarize files changed, tests run, risks, and next steps.',
].join('\n');

const PLACEHOLDER_RE = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;
const ANY_PLACEHOLDER_RE = /\{\{\s*[a-zA-Z0-9_]+\s*\}\}/;

/** Normalise a variable value to a string; arrays become newline lists. */
function valueToString(value: PromptVarValue): string {
    if (value == null) { return ''; }
    if (Array.isArray(value)) {
        const items = value.map(v => String(v).trim()).filter(Boolean);
        return items.join('\n');
    }
    return String(value).trim();
}

/** True when every non-empty line in the block is just a label ("foo:"). */
function isOnlyLabels(lines: string[]): boolean {
    const nonEmpty = lines.filter(l => l.trim().length > 0);
    if (nonEmpty.length === 0) { return true; }
    return nonEmpty.every(l => /:\s*$/.test(l.trim()));
}

/**
 * Build the final prompt. Present variables are substituted; blocks that end up
 * empty or label-only (because their variable was missing) are dropped.
 */
export function buildPrompt(template: string, vars: PromptVariables): string {
    const resolved: Record<string, string> = {};
    for (const [k, v] of Object.entries(vars)) {
        const s = valueToString(v);
        if (s) { resolved[k] = s; }
    }

    const blocks = template.split(/\n[ \t]*\n/);
    const kept: string[] = [];

    for (const block of blocks) {
        const substituted = block.replace(
            PLACEHOLDER_RE,
            (_m, name: string) => (name in resolved ? resolved[name] : '\u0000DROP\u0000'),
        );
        const lines = substituted
            .split('\n')
            .filter(line => !line.includes('\u0000DROP\u0000'));

        if (lines.length === 0 || isOnlyLabels(lines)) { continue; }
        if (ANY_PLACEHOLDER_RE.test(lines.join('\n'))) { continue; }
        kept.push(lines.join('\n').trimEnd());
    }

    return kept.join('\n\n').trim();
}
