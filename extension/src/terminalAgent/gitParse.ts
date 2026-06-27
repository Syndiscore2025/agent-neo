/**
 * AGENT NEO - Terminal Agent Orchestrator: Git output parsers
 *
 * Pure parsing of git CLI output. No `vscode`/`child_process` import so it is
 * unit-testable in isolation; the vscode-bound gatherer in contextGatherer.ts
 * consumes these.
 */

export interface GitStatusSummary {
    changedFiles: string[];
    stagedFiles: string[];
    unstagedFiles: string[];
    untracked: string[];
}

/** Parse `git log --oneline -n N` into trimmed one-line entries. */
export function parseRecentCommits(rawLog: string, limit = 5): string[] {
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
export function summarizeGitStatus(porcelain: string): GitStatusSummary {
    const staged = new Set<string>();
    const unstaged = new Set<string>();
    const untracked = new Set<string>();
    for (const raw of porcelain.split(/\r?\n/)) {
        if (raw.length < 3) { continue; }
        const x = raw[0];
        const y = raw[1];
        let p = raw.slice(3).trim();
        const arrow = p.indexOf(' -> ');
        if (arrow !== -1) { p = p.slice(arrow + 4).trim(); }
        if (!p) { continue; }
        if (x === '?' && y === '?') { untracked.add(p); continue; }
        if (x !== ' ' && x !== '?') { staged.add(p); }
        if (y !== ' ' && y !== '?') { unstaged.add(p); }
    }
    const changed = new Set<string>([...staged, ...unstaged, ...untracked]);
    return {
        changedFiles: [...changed],
        stagedFiles: [...staged],
        unstagedFiles: [...unstaged],
        untracked: [...untracked],
    };
}
