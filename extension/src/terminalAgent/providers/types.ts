/**
 * AGENT NEO - Terminal Agent Orchestrator: Provider types
 *
 * Provider-agnostic contract. Neo talks ONLY to TerminalAgentProvider; every
 * CLI-specific assumption (command shape, output parsing, completion markers)
 * lives inside a concrete adapter (e.g. AugmentCLIProvider).
 *
 * This file is intentionally free of any `vscode` import so the pure logic can
 * be unit-tested under vitest without the extension host.
 */

/** Resolved, host-supplied configuration for a single run. */
export interface ProviderConfig {
    /** Executable path/command, e.g. "auggie" or an absolute path. */
    cliPath: string;
    /** Working directory the CLI runs in. */
    workingDir: string;
    /** Hard timeout in seconds; 0 disables the timeout. */
    maxTimeoutSeconds: number;
    /** Whether stdout/stderr should be captured into the buffer. */
    captureOutput: boolean;
}

/**
 * Optional repo/editor context used for prompt building and command shaping.
 * Every field is optional — missing context is omitted cleanly, never injected
 * as null/undefined.
 */
export interface RunContext {
    repoPath?: string;
    currentBranch?: string;
    gitStatus?: string;
    changedFiles?: string[];
    recentCommits?: string[];
    openFiles?: string[];
    projectMemory?: string;
    providerName?: string;
    dateTime?: string;
}

/** A spawnable command, already split for child_process. */
export interface BuiltCommand {
    cmd: string;
    args: string[];
    /** True when the command must go through a shell (Windows .cmd/.ps1 shims). */
    useShell: boolean;
}

/** A coarse progress marker detected in agent output. */
export interface Milestone {
    label: string;
    raw: string;
}

/** An error-looking line detected in agent output. */
export interface DetectedError {
    message: string;
    raw: string;
}

/** Normalised view of raw agent output. */
export interface ParsedOutput {
    /** ANSI-stripped text. */
    text: string;
    milestones: Milestone[];
    errors: DetectedError[];
    completed: boolean;
}

/**
 * The single interface the rest of Neo depends on. Adapters implement this;
 * nothing outside an adapter may branch on a specific provider id.
 */
export interface TerminalAgentProvider {
    readonly id: string;
    readonly displayName: string;
    readonly executableName: string;
    readonly supportsStreaming: boolean;
    readonly supportsInteractiveInput: boolean;
    readonly supportsTerminalObservation: boolean;

    /** Build the spawnable command for a prompt + optional context. */
    buildCommand(config: ProviderConfig, prompt: string, context?: RunContext): BuiltCommand;

    /** Normalise raw output into text + milestones + errors + completion. */
    parseOutput(rawOutput: string): ParsedOutput;

    detectMilestones(output: string): Milestone[];
    detectErrors(output: string): DetectedError[];
    detectCompletion(output: string): boolean;
}

/** Strip ANSI escape sequences — shared by adapters. */
export const ANSI_RE = /\x1b\[[0-9;]*[A-Za-z]/g;

export function stripAnsi(s: string): string {
    return s.replace(ANSI_RE, '');
}
