/**
 * AGENT NEO - Terminal Agent Orchestrator: Process runner
 *
 * Generalised, provider-agnostic version of auggieRunner: spawns a BuiltCommand,
 * streams stdout/stderr as normalised events, and handles timeout + cancel.
 *
 * The spawn function is injectable so the runner can be unit-tested with a fake
 * ChildProcess (no real subprocess). No `vscode` import.
 */

import {
    spawn as nodeSpawn,
    ChildProcess,
    SpawnOptions,
} from 'child_process';
import { BuiltCommand, ProviderConfig, stripAnsi } from './providers/types';

export interface RunnerEvent {
    type: 'text' | 'stderr' | 'error' | 'finish' | 'timeout' | 'cancelled';
    content?: string;
    error?: string;
    code?: number | null;
}

export interface RunResult {
    ok: boolean;
    code: number | null;
    timedOut: boolean;
    cancelled: boolean;
    /** Combined ANSI-stripped output. Caller redacts before persisting. */
    output: string;
    pid: number | null;
}

export type SpawnFn = (
    cmd: string,
    args: string[],
    options: SpawnOptions,
) => ChildProcess;

export class ProcessRunner {
    private proc: ChildProcess | null = null;
    private cancelled = false;

    constructor(private readonly spawnFn: SpawnFn = nodeSpawn) {}

    isRunning(): boolean {
        return this.proc !== null;
    }

    pid(): number | null {
        return this.proc?.pid ?? null;
    }

    /** Cancel the active run, if any. Resolves the in-flight run as cancelled. */
    stop(): void {
        if (this.proc) {
            this.cancelled = true;
            try { this.proc.kill(); } catch { /* already gone */ }
        }
    }

    /**
     * Run a BuiltCommand to completion. Streams events via `onEvent` and
     * resolves with a RunResult. A non-zero exit is `ok:false` but not thrown.
     */
    run(
        built: BuiltCommand,
        config: ProviderConfig,
        onEvent?: (ev: RunnerEvent) => void,
    ): Promise<RunResult> {
        const emit = (ev: RunnerEvent) => { try { onEvent?.(ev); } catch { /* ignore */ } };
        return new Promise<RunResult>((resolve) => {
            if (this.proc) {
                emit({ type: 'error', error: 'A run is already in progress. Stop it first.' });
                resolve({ ok: false, code: null, timedOut: false, cancelled: false, output: '', pid: null });
                return;
            }

            this.cancelled = false;
            let output = '';
            let stderrBuf = '';
            let timedOut = false;
            let settled = false;
            const capture = config.captureOutput !== false;

            const options: SpawnOptions = {
                cwd: config.workingDir || undefined,
                shell: built.useShell,
                env: process.env,
            };

            let proc: ChildProcess;
            try {
                proc = this.spawnFn(built.cmd, built.args, options);
            } catch (err: any) {
                emit({ type: 'error', error: 'Failed to launch: ' + (err?.message || String(err)) });
                resolve({ ok: false, code: null, timedOut: false, cancelled: false, output: '', pid: null });
                return;
            }
            this.proc = proc;
            const pid = proc.pid ?? null;

            let timer: NodeJS.Timeout | null = null;
            if (config.maxTimeoutSeconds && config.maxTimeoutSeconds > 0) {
                timer = setTimeout(() => {
                    timedOut = true;
                    emit({ type: 'timeout', error: `Run exceeded ${config.maxTimeoutSeconds}s timeout.` });
                    try { proc.kill(); } catch { /* already gone */ }
                }, config.maxTimeoutSeconds * 1000);
            }

            const finish = (code: number | null) => {
                if (settled) { return; }
                settled = true;
                if (timer) { clearTimeout(timer); }
                this.proc = null;
                const cancelled = this.cancelled;
                if (cancelled) { emit({ type: 'cancelled' }); }
                emit({ type: 'finish', code });
                resolve({ ok: code === 0 && !timedOut && !cancelled, code, timedOut, cancelled, output, pid });
            };

            proc.stdout?.on('data', (chunk: Buffer) => {
                const text = stripAnsi(chunk.toString());
                if (capture) { output += text; }
                if (text) { emit({ type: 'text', content: text }); }
            });
            proc.stderr?.on('data', (chunk: Buffer) => {
                const text = stripAnsi(chunk.toString());
                stderrBuf += text;
                if (capture) { output += text; }
                if (text) { emit({ type: 'stderr', content: text }); }
            });
            proc.on('error', (err: any) => {
                const notFound = err && err.code === 'ENOENT';
                emit({
                    type: 'error',
                    error: notFound
                        ? `CLI not found: "${built.cmd}". Check the configured CLI path.`
                        : 'Process error: ' + (err?.message || String(err)),
                });
                finish(null);
            });
            proc.on('close', (code) => finish(code));
        });
    }
}
