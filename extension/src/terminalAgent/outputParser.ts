/**
 * AGENT NEO - Terminal Agent Orchestrator: Output parser
 *
 * Normalises a finished run's raw output into structured signals: milestones
 * and errors (delegated to the provider so CLI-specific heuristics stay in the
 * adapter), plus provider-agnostic detection of test results, claimed file
 * edits, commit claims, and warnings. Pure — no `vscode`.
 */

import { TerminalAgentProvider, Milestone, DetectedError, stripAnsi } from './providers/types';

export interface TestResults {
    detected: boolean;
    passed: number;
    failed: number;
}

export interface ParsedRun {
    milestones: Milestone[];
    errors: DetectedError[];
    warnings: string[];
    completed: boolean;
    tests: TestResults;
    /** Files the agent SAYS it changed (claims, not yet verified vs git). */
    claimedFiles: string[];
    claimedCommit: boolean;
    commitHashes: string[];
}

/** Highest captured count for a regex with one numeric group (robust to repeats). */
function maxCount(text: string, re: RegExp): number {
    let max = 0;
    for (const m of text.matchAll(re)) {
        const n = parseInt(m[1], 10);
        if (!Number.isNaN(n) && n > max) { max = n; }
    }
    return max;
}

/** Detect a test summary across common runners (jest/vitest/pytest/mocha/go). */
export function detectTestResults(output: string): TestResults {
    const text = stripAnsi(output);
    const passed = maxCount(text, /(\d+)\s+(?:tests?\s+)?(?:passed|passing)\b/gi);
    const failed = maxCount(text, /(\d+)\s+(?:tests?\s+)?(?:failed|failing)\b/gi);
    const mentioned = /\btest(?:s|ing|\s+suite|\s+run)?\b/i.test(text);
    return { detected: passed > 0 || failed > 0 || (mentioned && /\b(ran|run|suite)\b/i.test(text)), passed, failed };
}

const CLAIM_RE =
    /\b(?:created|wrote|writing|edit(?:ed|ing)?|modif(?:y|ied)|updat(?:e|ed|ing)|add(?:ed|ing)?|delet(?:e|ed|ing)|remov(?:e|ed|ing))\b[^\n]*?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)/gi;

/** Files the agent claims it touched, de-duplicated and separator-normalised. */
export function extractClaimedFiles(output: string): string[] {
    const text = stripAnsi(output);
    const out = new Set<string>();
    for (const m of text.matchAll(CLAIM_RE)) {
        const p = m[1].replace(/\\/g, '/').replace(/^\.\//, '').trim();
        if (p && !p.startsWith('http') && !p.includes('//')) { out.add(p); }
    }
    return [...out];
}

/** Detect commit claims + any explicit short/long commit hashes. */
export function detectCommitClaims(output: string): { claimedCommit: boolean; commitHashes: string[] } {
    const text = stripAnsi(output);
    const hashes = new Set<string>();
    for (const m of text.matchAll(/\[[^\]\n]*\s([0-9a-f]{7,40})\]/gi)) { hashes.add(m[1]); }
    for (const m of text.matchAll(/\bcommit\s+([0-9a-f]{7,40})\b/gi)) { hashes.add(m[1]); }
    const nothing = /\bnothing to commit\b|\bno changes added to commit\b/i.test(text);
    const claimed = hashes.size > 0 || (!nothing && /\bcommit(?:ted|ting|s)?\b/i.test(text));
    return { claimedCommit: claimed, commitHashes: [...hashes] };
}

/** Warning-looking lines (excluding ones that read as errors). */
export function detectWarnings(output: string): string[] {
    const out: string[] = [];
    for (const raw of stripAnsi(output).split(/\r?\n/)) {
        const line = raw.trim();
        if (line && /\bwarn(?:ing)?\b/i.test(line) && !/\berror\b/i.test(line)) {
            out.push(line.slice(0, 300));
        }
    }
    return out.slice(0, 50);
}

/** Full parse of a finished run, delegating milestone/error heuristics to the provider. */
export function parseRun(provider: TerminalAgentProvider, rawOutput: string): ParsedRun {
    const parsed = provider.parseOutput(rawOutput);
    const commit = detectCommitClaims(rawOutput);
    return {
        milestones: parsed.milestones,
        errors: parsed.errors,
        warnings: detectWarnings(rawOutput),
        completed: parsed.completed,
        tests: detectTestResults(rawOutput),
        claimedFiles: extractClaimedFiles(rawOutput),
        claimedCommit: commit.claimedCommit,
        commitHashes: commit.commitHashes,
    };
}

export type { Milestone, DetectedError };
