"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Git output parsers
 *
 * Pure parsing of git CLI output. No `vscode`/`child_process` import so it is
 * unit-testable in isolation; the vscode-bound gatherer in contextGatherer.ts
 * consumes these.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.parseRecentCommits = parseRecentCommits;
exports.summarizeGitStatus = summarizeGitStatus;
/** Parse `git log --oneline -n N` into trimmed one-line entries. */
function parseRecentCommits(rawLog, limit = 5) {
    return rawLog
        .split(/\r?\n/)
        .map(l => l.trim())
        .filter(Boolean)
        .slice(0, limit);
}
/**
 * Parse `git status --porcelain` into staged/unstaged/untracked/changed sets.
 * Lines are "XY path"; renames ("old -> new") resolve to the new path.
 */
function summarizeGitStatus(porcelain) {
    const staged = new Set();
    const unstaged = new Set();
    const untracked = new Set();
    for (const raw of porcelain.split(/\r?\n/)) {
        if (raw.length < 3) {
            continue;
        }
        const x = raw[0];
        const y = raw[1];
        let p = raw.slice(3).trim();
        const arrow = p.indexOf(' -> ');
        if (arrow !== -1) {
            p = p.slice(arrow + 4).trim();
        }
        if (!p) {
            continue;
        }
        if (x === '?' && y === '?') {
            untracked.add(p);
            continue;
        }
        if (x !== ' ' && x !== '?') {
            staged.add(p);
        }
        if (y !== ' ' && y !== '?') {
            unstaged.add(p);
        }
    }
    const changed = new Set([...staged, ...unstaged, ...untracked]);
    return {
        changedFiles: [...changed],
        stagedFiles: [...staged],
        unstagedFiles: [...unstaged],
        untracked: [...untracked],
    };
}
//# sourceMappingURL=gitParse.js.map