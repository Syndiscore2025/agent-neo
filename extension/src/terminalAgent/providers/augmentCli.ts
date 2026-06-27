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

import {
    TerminalAgentProvider,
    ProviderConfig,
    RunContext,
    BuiltCommand,
    ParsedOutput,
    Milestone,
    DetectedError,
    stripAnsi,
} from './types';

/** Lines that indicate the agent is making progress. */
const MILESTONE_RE =
    /^\s*(creating|created|editing|edited|writing|wrote|adding|added|updating|updated|deleting|deleted|running|ran|installing|installed|committed|commit|test[s]?\b)\b.*/i;

/** Lines that look like an error/failure. */
const ERROR_RE = /(error|exception|traceback|failed|failure|cannot|not found|enoent)\b/i;

/** Markers that the agent considers the task finished. */
const COMPLETION_RE =
    /(summary|files changed|tests run|next steps|done\b|completed\b|finished\b)/i;

export class AugmentCLIProvider implements TerminalAgentProvider {
    readonly id = 'augment-cli';
    readonly displayName = 'Augment CLI';
    readonly executableName = 'auggie';
    readonly supportsStreaming = true;
    readonly supportsInteractiveInput = false;
    readonly supportsTerminalObservation = true;

    /**
     * `auggie --print "<prompt>"`. On Windows we spawn through a shell to
     * resolve the auggie.cmd/.ps1 shims, so the whole prompt must arrive as a
     * single quoted argument (cmd.exe would otherwise re-split on whitespace).
     */
    buildCommand(config: ProviderConfig, prompt: string, _context?: RunContext): BuiltCommand {
        const cmd = (config.cliPath || this.executableName).trim() || this.executableName;
        const useShell = process.platform === 'win32';
        const promptArg = useShell ? '"' + prompt.replace(/"/g, '""') + '"' : prompt;
        return { cmd, args: ['--print', promptArg], useShell };
    }

    parseOutput(rawOutput: string): ParsedOutput {
        const text = stripAnsi(rawOutput);
        return {
            text,
            milestones: this.detectMilestones(text),
            errors: this.detectErrors(text),
            completed: this.detectCompletion(text),
        };
    }

    detectMilestones(output: string): Milestone[] {
        const out: Milestone[] = [];
        for (const raw of stripAnsi(output).split(/\r?\n/)) {
            const line = raw.trim();
            if (!line) { continue; }
            const m = line.match(MILESTONE_RE);
            if (m) { out.push({ label: m[1].toLowerCase(), raw: line }); }
        }
        return out;
    }

    detectErrors(output: string): DetectedError[] {
        const out: DetectedError[] = [];
        for (const raw of stripAnsi(output).split(/\r?\n/)) {
            const line = raw.trim();
            if (line && ERROR_RE.test(line)) {
                out.push({ message: line.slice(0, 300), raw: line });
            }
        }
        return out;
    }

    detectCompletion(output: string): boolean {
        return COMPLETION_RE.test(stripAnsi(output));
    }
}
