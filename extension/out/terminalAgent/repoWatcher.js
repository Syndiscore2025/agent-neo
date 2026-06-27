"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Repo watcher
 *
 * Snapshots the git working tree (branch / staged / unstaged / untracked /
 * changed / recent commits), diffs two snapshots, and verifies a CLI agent's
 * CLAIMS against what actually changed on disk. Pure: builds snapshots from raw
 * git output via gitParse, so all logic is unit-testable without spawning git.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildRepoState = buildRepoState;
exports.diffRepoState = diffRepoState;
exports.verifyClaims = verifyClaims;
const gitParse_1 = require("./gitParse");
/** Build a normalised snapshot from raw `git` outputs. */
function buildRepoState(branch, statusPorcelain, logOneline, commitLimit = 20) {
    const s = (0, gitParse_1.summarizeGitStatus)(statusPorcelain);
    return {
        branch: branch.trim() || null,
        staged: s.stagedFiles,
        unstaged: s.unstagedFiles,
        untracked: s.untracked,
        changed: s.changedFiles,
        commits: (0, gitParse_1.parseRecentCommits)(logOneline, commitLimit),
    };
}
/** Items present in `after` but not in `before`, order-preserved. */
function added(before, after) {
    const seen = new Set(before);
    return after.filter(x => !seen.has(x));
}
/** Diff two snapshots: what changed between a pre-run and post-run state. */
function diffRepoState(before, after) {
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
function norm(p) {
    return p.replace(/\\/g, '/').replace(/^\.\//, '').trim();
}
/**
 * Compare what the agent CLAIMED (parsed from its output) against the real
 * working-tree change set (`diffRepoState` result). Path comparison is
 * separator-normalised so Windows `\` vs `/` never causes false mismatches.
 */
function verifyClaims(claimedFiles, claimedCommit, diff) {
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
//# sourceMappingURL=repoWatcher.js.map