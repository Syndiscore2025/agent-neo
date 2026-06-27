/**
 * AGENT NEO - Terminal Agent Orchestrator: Repo watcher
 *
 * Snapshots the git working tree (branch / staged / unstaged / untracked /
 * changed / recent commits), diffs two snapshots, and verifies a CLI agent's
 * CLAIMS against what actually changed on disk. Pure: builds snapshots from raw
 * git output via gitParse, so all logic is unit-testable without spawning git.
 */

import { summarizeGitStatus, parseRecentCommits } from './gitParse';

export interface RepoState {
    branch: string | null;
    staged: string[];
    unstaged: string[];
    untracked: string[];
    changed: string[];
    commits: string[];
}

export interface RepoStateDiff {
    branchChanged: boolean;
    previousBranch: string | null;
    currentBranch: string | null;
    newlyChanged: string[];
    newlyStaged: string[];
    newlyUnstaged: string[];
    newlyUntracked: string[];
    newCommits: string[];
}

/** Build a normalised snapshot from raw `git` outputs. */
export function buildRepoState(
    branch: string,
    statusPorcelain: string,
    logOneline: string,
    commitLimit = 20,
): RepoState {
    const s = summarizeGitStatus(statusPorcelain);
    return {
        branch: branch.trim() || null,
        staged: s.stagedFiles,
        unstaged: s.unstagedFiles,
        untracked: s.untracked,
        changed: s.changedFiles,
        commits: parseRecentCommits(logOneline, commitLimit),
    };
}

/** Items present in `after` but not in `before`, order-preserved. */
function added(before: string[], after: string[]): string[] {
    const seen = new Set(before);
    return after.filter(x => !seen.has(x));
}

/** Diff two snapshots: what changed between a pre-run and post-run state. */
export function diffRepoState(before: RepoState, after: RepoState): RepoStateDiff {
    return {
        branchChanged: before.branch !== after.branch,
        previousBranch: before.branch,
        currentBranch: after.branch,
        newlyChanged: added(before.changed, after.changed),
        newlyStaged: added(before.staged, after.staged),
        newlyUnstaged: added(before.unstaged, after.unstaged),
        newlyUntracked: added(before.untracked, after.untracked),
        newCommits: added(before.commits, after.commits),
    };
}

export interface ClaimVerification {
    /** Files the CLI said it changed (from parsed output). */
    claimedFiles: string[];
    /** Files that actually changed on disk this run. */
    actuallyChanged: string[];
    /** Claimed AND actually changed. */
    verified: string[];
    /** Claimed but NOT changed — possible hallucination / no-op. */
    unverifiedClaims: string[];
    /** Changed but NOT claimed — silent edits worth surfacing. */
    unclaimedChanges: string[];
    /** Whether the CLI claimed it created a commit. */
    claimedCommit: boolean;
    /** Commits actually created this run. */
    commitsCreated: string[];
    /** Commit claim matches reality (claim ⇔ at least one new commit). */
    commitClaimConsistent: boolean;
}

function norm(p: string): string {
    return p.replace(/\\/g, '/').replace(/^\.\//, '').trim();
}

/**
 * Compare what the agent CLAIMED (parsed from its output) against the real
 * working-tree change set (`diffRepoState` result). Path comparison is
 * separator-normalised so Windows `\` vs `/` never causes false mismatches.
 */
export function verifyClaims(
    claimedFiles: string[],
    claimedCommit: boolean,
    diff: RepoStateDiff,
): ClaimVerification {
    const claimed = [...new Set(claimedFiles.map(norm).filter(Boolean))];
    const changed = diff.newlyChanged.map(norm);
    const changedSet = new Set(changed);
    const claimedSet = new Set(claimed);

    const verified = claimed.filter(f => changedSet.has(f));
    const unverifiedClaims = claimed.filter(f => !changedSet.has(f));
    const unclaimedChanges = changed.filter(f => !claimedSet.has(f));
    const commitsCreated = diff.newCommits;

    return {
        claimedFiles: claimed,
        actuallyChanged: changed,
        verified,
        unverifiedClaims,
        unclaimedChanges,
        claimedCommit,
        commitsCreated,
        commitClaimConsistent: claimedCommit === (commitsCreated.length > 0),
    };
}
