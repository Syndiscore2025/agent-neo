"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Augment CLI provider
 *
 * The FIRST provider adapter. ALL Augment/Auggie-specific assumptions live
 * here: command shape (`auggie --print "<prompt>"`), Windows shell-quoting,
 * and heuristic milestone/error/completion detection. The rest of Neo never
 * references "auggie" directly — it goes through TerminalAgentProvider.
 *
 * No `vscode` import: this stays unit-testable in isolation.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AugmentCLIProvider = void 0;
const types_1 = require("./types");
/** Lines that indicate the agent is making progress. */
const MILESTONE_RE = /^\s*(creating|created|editing|edited|writing|wrote|adding|added|updating|updated|deleting|deleted|running|ran|installing|installed|committed|commit|test[s]?\b)\b.*/i;
/** Lines that look like an error/failure. */
const ERROR_RE = /(error|exception|traceback|failed|failure|cannot|not found|enoent)\b/i;
/** Markers that the agent considers the task finished. */
const COMPLETION_RE = /(summary|files changed|tests run|next steps|done\b|completed\b|finished\b)/i;
class AugmentCLIProvider {
    constructor() {
        this.id = 'augment-cli';
        this.displayName = 'Augment CLI';
        this.executableName = 'auggie';
        this.supportsStreaming = true;
        this.supportsInteractiveInput = false;
        this.supportsTerminalObservation = true;
    }
    /**
     * `auggie --print "<prompt>"`. On Windows we spawn through a shell to
     * resolve the auggie.cmd/.ps1 shims, so the whole prompt must arrive as a
     * single quoted argument (cmd.exe would otherwise re-split on whitespace).
     */
    buildCommand(config, prompt, _context) {
        const cmd = (config.cliPath || this.executableName).trim() || this.executableName;
        const useShell = process.platform === 'win32';
        const promptArg = useShell ? '"' + prompt.replace(/"/g, '""') + '"' : prompt;
        return { cmd, args: ['--print', promptArg], useShell };
    }
    parseOutput(rawOutput) {
        const text = (0, types_1.stripAnsi)(rawOutput);
        return {
            text,
            milestones: this.detectMilestones(text),
            errors: this.detectErrors(text),
            completed: this.detectCompletion(text),
        };
    }
    detectMilestones(output) {
        const out = [];
        for (const raw of (0, types_1.stripAnsi)(output).split(/\r?\n/)) {
            const line = raw.trim();
            if (!line) {
                continue;
            }
            const m = line.match(MILESTONE_RE);
            if (m) {
                out.push({ label: m[1].toLowerCase(), raw: line });
            }
        }
        return out;
    }
    detectErrors(output) {
        const out = [];
        for (const raw of (0, types_1.stripAnsi)(output).split(/\r?\n/)) {
            const line = raw.trim();
            if (line && ERROR_RE.test(line)) {
                out.push({ message: line.slice(0, 300), raw: line });
            }
        }
        return out;
    }
    detectCompletion(output) {
        return COMPLETION_RE.test((0, types_1.stripAnsi)(output));
    }
}
exports.AugmentCLIProvider = AugmentCLIProvider;
//# sourceMappingURL=augmentCli.js.map