"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Context gatherer
 *
 * Collects repo/editor context for prompt building and post-run comparison.
 * The git-output parsers are PURE (unit-tested); gatherRunContext is the thin
 * vscode/child_process-bound entry the extension calls.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.summarizeGitStatus = exports.parseRecentCommits = void 0;
exports.gatherRunContext = gatherRunContext;
exports.getPostRunStatus = getPostRunStatus;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const gitParse_1 = require("./gitParse");
Object.defineProperty(exports, "parseRecentCommits", { enumerable: true, get: function () { return gitParse_1.parseRecentCommits; } });
Object.defineProperty(exports, "summarizeGitStatus", { enumerable: true, get: function () { return gitParse_1.summarizeGitStatus; } });
/** Run git best-effort; resolves '' on any failure (missing git / non-repo). */
function git(args, cwd) {
    return new Promise(resolve => {
        (0, child_process_1.execFile)('git', args, { cwd, windowsHide: true }, (err, stdout) => {
            resolve(err ? '' : (stdout || '').toString());
        });
    });
}
/** Open, file-backed editor documents as repo-relative paths (bounded). */
function openFiles() {
    return vscode.workspace.textDocuments
        .filter(d => !d.isUntitled && d.uri.scheme === 'file')
        .map(d => vscode.workspace.asRelativePath(d.uri))
        .slice(0, 20);
}
/** Gather the full run context for prompt building. */
async function gatherRunContext(repoPath, providerName) {
    const [branch, status, log] = await Promise.all([
        git(['rev-parse', '--abbrev-ref', 'HEAD'], repoPath),
        git(['status', '--porcelain'], repoPath),
        // Same depth as getPostRunStatus (20) so the pre/post commit diff only
        // reports commits genuinely created during the run — not pre-existing
        // history that simply falls outside a shorter pre-run window.
        git(['log', '--oneline', '-n', '20'], repoPath),
    ]);
    const summary = (0, gitParse_1.summarizeGitStatus)(status);
    return {
        repoPath,
        currentBranch: branch.trim() || undefined,
        gitStatus: status.trim() || undefined,
        changedFiles: summary.changedFiles.length ? summary.changedFiles : undefined,
        recentCommits: (0, gitParse_1.parseRecentCommits)(log, 20),
        openFiles: openFiles(),
        providerName,
        dateTime: new Date().toISOString(),
    };
}
/** Re-read branch + working-tree status + recent commits after a run, for claim verification. */
async function getPostRunStatus(repoPath) {
    const [branch, status, log] = await Promise.all([
        git(['rev-parse', '--abbrev-ref', 'HEAD'], repoPath),
        git(['status', '--porcelain'], repoPath),
        git(['log', '--oneline', '-n', '20'], repoPath),
    ]);
    return {
        branch: branch.trim() || null,
        commits: (0, gitParse_1.parseRecentCommits)(log, 20),
        ...(0, gitParse_1.summarizeGitStatus)(status),
    };
}
//# sourceMappingURL=contextGatherer.js.map