"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Process runner
 *
 * Generalised, provider-agnostic version of auggieRunner: spawns a BuiltCommand,
 * streams stdout/stderr as normalised events, and handles timeout + cancel.
 *
 * The spawn function is injectable so the runner can be unit-tested with a fake
 * ChildProcess (no real subprocess). No `vscode` import.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ProcessRunner = void 0;
const child_process_1 = require("child_process");
const types_1 = require("./providers/types");
class ProcessRunner {
    constructor(spawnFn = child_process_1.spawn) {
        this.spawnFn = spawnFn;
        this.proc = null;
        this.cancelled = false;
    }
    isRunning() {
        return this.proc !== null;
    }
    pid() {
        return this.proc?.pid ?? null;
    }
    /** Cancel the active run, if any. Resolves the in-flight run as cancelled. */
    stop() {
        if (this.proc) {
            this.cancelled = true;
            try {
                this.proc.kill();
            }
            catch { /* already gone */ }
        }
    }
    /**
     * Run a BuiltCommand to completion. Streams events via `onEvent` and
     * resolves with a RunResult. A non-zero exit is `ok:false` but not thrown.
     */
    run(built, config, onEvent) {
        const emit = (ev) => { try {
            onEvent?.(ev);
        }
        catch { /* ignore */ } };
        return new Promise((resolve) => {
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
            const options = {
                cwd: config.workingDir || undefined,
                shell: built.useShell,
                env: process.env,
            };
            let proc;
            try {
                proc = this.spawnFn(built.cmd, built.args, options);
            }
            catch (err) {
                emit({ type: 'error', error: 'Failed to launch: ' + (err?.message || String(err)) });
                resolve({ ok: false, code: null, timedOut: false, cancelled: false, output: '', pid: null });
                return;
            }
            this.proc = proc;
            const pid = proc.pid ?? null;
            let timer = null;
            if (config.maxTimeoutSeconds && config.maxTimeoutSeconds > 0) {
                timer = setTimeout(() => {
                    timedOut = true;
                    emit({ type: 'timeout', error: `Run exceeded ${config.maxTimeoutSeconds}s timeout.` });
                    try {
                        proc.kill();
                    }
                    catch { /* already gone */ }
                }, config.maxTimeoutSeconds * 1000);
            }
            const finish = (code) => {
                if (settled) {
                    return;
                }
                settled = true;
                if (timer) {
                    clearTimeout(timer);
                }
                this.proc = null;
                const cancelled = this.cancelled;
                if (cancelled) {
                    emit({ type: 'cancelled' });
                }
                emit({ type: 'finish', code });
                resolve({ ok: code === 0 && !timedOut && !cancelled, code, timedOut, cancelled, output, pid });
            };
            proc.stdout?.on('data', (chunk) => {
                const text = (0, types_1.stripAnsi)(chunk.toString());
                if (capture) {
                    output += text;
                }
                if (text) {
                    emit({ type: 'text', content: text });
                }
            });
            proc.stderr?.on('data', (chunk) => {
                const text = (0, types_1.stripAnsi)(chunk.toString());
                stderrBuf += text;
                if (capture) {
                    output += text;
                }
                if (text) {
                    emit({ type: 'stderr', content: text });
                }
            });
            proc.on('error', (err) => {
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
exports.ProcessRunner = ProcessRunner;
//# sourceMappingURL=processRunner.js.map