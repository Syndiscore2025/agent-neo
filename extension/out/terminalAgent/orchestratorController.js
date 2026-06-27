"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Controller
 *
 * Sequences a single Prompt-Orchestrator run: gather context → build prompt →
 * review/edit → launch the provider's command → stream output → persist a
 * non-secret session summary. Deliberately free of any `vscode` import — every
 * side effect (UI, context, persistence) is injected, so the flow is unit-
 * testable end to end.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.OrchestratorController = void 0;
const registry_1 = require("./providers/registry");
const promptBuilder_1 = require("./promptBuilder");
const processRunner_1 = require("./processRunner");
const session_1 = require("./session");
const outputParser_1 = require("./outputParser");
const repoWatcher_1 = require("./repoWatcher");
const safetyDetector_1 = require("./safetyDetector");
const suggestionEngine_1 = require("./suggestionEngine");
class OrchestratorController {
    constructor(deps) {
        this.deps = deps;
        this.session = null;
        this.runner = deps.runner ?? new processRunner_1.ProcessRunner();
    }
    isRunning() {
        return this.runner.isRunning();
    }
    stop() {
        this.runner.stop();
    }
    /** Run the full orchestrate-and-stream flow. Returns the session, or null if cancelled. */
    async start(userRequest, repoPath) {
        const { post, settings } = this.deps;
        const provider = (0, registry_1.getProviderRegistry)().get(settings.defaultProvider) ??
            (0, registry_1.getProviderRegistry)().list()[0];
        if (!provider) {
            post({ type: 'streamEvent', event: { type: 'error', error: 'No terminal-agent provider is registered.' } });
            return null;
        }
        const context = await this.deps.gatherContext(repoPath, provider.displayName);
        const generated = (0, promptBuilder_1.buildPrompt)(settings.promptTemplate || promptBuilder_1.DEFAULT_PROMPT_TEMPLATE, {
            repo_path: context.repoPath,
            current_branch: context.currentBranch,
            user_request: userRequest,
            project_memory: context.projectMemory,
            open_files: context.openFiles,
            git_status: context.gitStatus,
            changed_files: context.changedFiles,
            recent_commits: context.recentCommits,
            provider_name: provider.displayName,
            date_time: context.dateTime,
        });
        const edited = await this.deps.reviewPrompt(generated);
        if (edited === undefined) {
            return null;
        } // cancelled at review
        const session = (0, session_1.createSession)({
            provider_id: provider.id,
            provider_name: provider.displayName,
            repo_path: repoPath,
            original_user_request: userRequest,
            generated_prompt: generated,
            edited_prompt: edited,
            current_branch_at_start: context.currentBranch ?? null,
            status: 'running',
        });
        this.session = session;
        post({ type: 'streamRunStart', task: userRequest, preRunRef: null });
        const config = {
            cliPath: settings.cliPath,
            workingDir: repoPath,
            maxTimeoutSeconds: settings.maxTimeoutSeconds,
            captureOutput: settings.captureOutput,
        };
        const built = provider.buildCommand(config, edited, context);
        const result = await this.runner.run(built, config, ev => this.onEvent(session, ev));
        const status = await this.deps.getPostRunStatus(repoPath);
        session.current_branch_current = status.branch;
        session.changed_files = status.changedFiles;
        session.staged_files = status.stagedFiles;
        session.unstaged_files = status.unstagedFiles;
        const finalStatus = result.cancelled
            ? 'cancelled'
            : result.timedOut || !result.ok
                ? 'failed'
                : 'completed';
        (0, session_1.endSession)(session, finalStatus);
        // Phase 5 — intelligence + safety: parse output, verify claims vs the
        // real working tree, flag dangerous commands, and derive next steps.
        const parsed = (0, outputParser_1.parseRun)(provider, result.output);
        const before = (0, repoWatcher_1.buildRepoState)(context.currentBranch ?? '', context.gitStatus ?? '', (context.recentCommits ?? []).join('\n'));
        const after = {
            branch: status.branch,
            staged: status.stagedFiles,
            unstaged: status.unstagedFiles,
            untracked: status.untracked ?? [],
            changed: status.changedFiles,
            commits: status.commits ?? [],
        };
        const diff = (0, repoWatcher_1.diffRepoState)(before, after);
        const verification = (0, repoWatcher_1.verifyClaims)(parsed.claimedFiles, parsed.claimedCommit, diff);
        const safetyFlags = (0, safetyDetector_1.detectDangerousCommands)(result.output);
        session.parsed_milestones = parsed.milestones;
        session.detected_errors = parsed.errors;
        session.detected_warnings = parsed.warnings;
        session.tests_detected = parsed.tests.detected;
        session.tests_passed = parsed.tests.passed;
        session.tests_failed = parsed.tests.failed;
        session.commits_created = diff.newCommits;
        session.safety_flags = safetyFlags;
        session.suggestions = (0, suggestionEngine_1.buildSuggestions)({
            status: finalStatus,
            parsed,
            verification,
            changedFiles: status.changedFiles,
            branchChanged: diff.branchChanged,
            commitsCreated: diff.newCommits,
            safetyFlags,
            userRequest,
        });
        const summary = this.buildSummary(session, finalStatus);
        session.final_summary = summary;
        const files = status.changedFiles.map(p => ({ path: p }));
        post({
            type: 'streamEvent',
            event: {
                type: 'finish',
                success: finalStatus === 'completed',
                files,
                summary,
                suggestions: session.suggestions,
                tests: parsed.tests,
                safetyFlags,
                verification: {
                    verified: verification.verified,
                    unverifiedClaims: verification.unverifiedClaims,
                    unclaimedChanges: verification.unclaimedChanges,
                    commitsCreated: diff.newCommits,
                },
            },
        });
        post({ type: 'streamRunDone' });
        if (settings.autoSaveSummaries) {
            await this.deps.history.save(session);
        }
        return session;
    }
    onEvent(session, ev) {
        if (ev.type === 'text' || ev.type === 'stderr') {
            if (ev.content) {
                // Redact before it is buffered or displayed — secret values must
                // never reach the UI or any in-memory store.
                const safe = (0, safetyDetector_1.redactSecrets)(ev.content);
                (0, session_1.appendOutput)(session, safe);
                this.deps.post({ type: 'streamEvent', event: { type: 'text', content: safe } });
            }
        }
        else if (ev.type === 'error' || ev.type === 'timeout') {
            this.deps.post({ type: 'streamEvent', event: { type: 'error', error: ev.error || 'Run error.' } });
        }
    }
    buildSummary(session, status) {
        const n = session.changed_files.length;
        const committed = session.commits_created.length;
        const head = `${session.provider_name} run ${status}.`;
        const files = n
            ? ` ${n} changed file(s)${committed ? ` and ${committed} new commit(s)` : ''} — review before pushing; nothing was pushed.`
            : (committed
                ? ` ${committed} new commit(s) created — review before pushing.`
                : ' No file changes detected.');
        const tests = session.tests_detected
            ? ` Tests: ${session.tests_passed} passed, ${session.tests_failed} failed.`
            : '';
        const errs = session.detected_errors.length
            ? ` ${session.detected_errors.length} error(s) detected.`
            : '';
        return head + files + tests + errs;
    }
}
exports.OrchestratorController = OrchestratorController;
//# sourceMappingURL=orchestratorController.js.map