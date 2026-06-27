/**
 * AGENT NEO - Terminal Agent Orchestrator: Context gatherer
 *
 * Collects repo/editor context for prompt building and post-run comparison.
 * The git-output parsers are PURE (unit-tested); gatherRunContext is the thin
 * vscode/child_process-bound entry the extension calls.
 */

import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { RunContext } from './providers/types';
import {
    GitStatusSummary,
    parseRecentCommits,
    summarizeGitStatus,
} from './gitParse';

export { GitStatusSummary, parseRecentCommits, summarizeGitStatus };

export interface PostRunStatus extends GitStatusSummary {
    branch: string | null;
    commits: string[];
}

/** Run git best-effort; resolves '' on any failure (missing git / non-repo). */
function git(args: string[], cwd: string): Promise<string> {
    return new Promise(resolve => {
        execFile('git', args, { cwd, windowsHide: true }, (err, stdout) => {
            resolve(err ? '' : (stdout || '').toString());
        });
    });
}

/** Open, file-backed editor documents as repo-relative paths (bounded). */
function openFiles(): string[] {
    return vscode.workspace.textDocuments
        .filter(d => !d.isUntitled && d.uri.scheme === 'file')
        .map(d => vscode.workspace.asRelativePath(d.uri))
        .slice(0, 20);
}

/** Gather the full run context for prompt building. */
export async function gatherRunContext(
    repoPath: string,
    providerName: string,
): Promise<RunContext> {
    const [branch, status, log] = await Promise.all([
        git(['rev-parse', '--abbrev-ref', 'HEAD'], repoPath),
        git(['status', '--porcelain'], repoPath),
        git(['log', '--oneline', '-n', '5'], repoPath),
    ]);
    const summary = summarizeGitStatus(status);
    return {
        repoPath,
        currentBranch: branch.trim() || undefined,
        gitStatus: status.trim() || undefined,
        changedFiles: summary.changedFiles.length ? summary.changedFiles : undefined,
        recentCommits: parseRecentCommits(log),
        openFiles: openFiles(),
        providerName,
        dateTime: new Date().toISOString(),
    };
}

/** Re-read branch + working-tree status + recent commits after a run, for claim verification. */
export async function getPostRunStatus(repoPath: string): Promise<PostRunStatus> {
    const [branch, status, log] = await Promise.all([
        git(['rev-parse', '--abbrev-ref', 'HEAD'], repoPath),
        git(['status', '--porcelain'], repoPath),
        git(['log', '--oneline', '-n', '20'], repoPath),
    ]);
    return {
        branch: branch.trim() || null,
        commits: parseRecentCommits(log, 20),
        ...summarizeGitStatus(status),
    };
}
