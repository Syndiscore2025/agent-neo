/**
 * AGENT NEO - Auggie Runner
 * Runs the Auggie CLI as a local subprocess so it can act as an alternate
 * agent backend. Output is streamed back as normalized events that the chat
 * webview already understands (text / error / finish).
 */

import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';

export interface AuggieEvent {
    type: string;
    [key: string]: any;
}

const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;

export class AuggieRunner {
    private proc: ChildProcess | null = null;

    public isRunning(): boolean {
        return this.proc !== null;
    }

    /**
     * Kill the active Auggie process, if any.
     */
    public stop(): void {
        if (this.proc) {
            try { this.proc.kill(); } catch { /* already gone */ }
            this.proc = null;
        }
    }

    /**
     * List the models Auggie offers via `auggie model list`, parsed into
     * { id, label } pairs (id is the bracketed short name, e.g. "opus4.8").
     * Best-effort: resolves to [] if the CLI is missing, not logged in, or the
     * output can't be parsed.
     */
    public listModels(): Promise<{ id: string; label: string }[]> {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get<string>('auggiePath', 'auggie');
            let proc: ChildProcess;
            try {
                proc = spawn(cmd, ['model', 'list'], {
                    shell: process.platform === 'win32',
                    env: process.env,
                });
            } catch {
                resolve([]);
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c: Buffer) => { buf += c.toString(); });
            proc.on('error', () => resolve([]));
            proc.on('close', () => {
                const out: { id: string; label: string }[] = [];
                for (const raw of buf.replace(ANSI, '').split(/\r?\n/)) {
                    const m = raw.match(/^\s*-\s*(.+?)\s*\[([^\]]+)\]\s*$/);
                    if (m) { out.push({ label: m[1].trim(), id: m[2].trim() }); }
                }
                resolve(out);
            });
        });
    }

    /**
     * Return the id of the most recent Auggie session saved for `cwd`, or null.
     * Used to give the chat thread continuous memory: we resume this id on the
     * next run so Auggie remembers the previous exchange. Best-effort.
     */
    public getLatestSessionId(cwd: string): Promise<string | null> {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get<string>('auggiePath', 'auggie');
            let proc: ChildProcess;
            try {
                proc = spawn(cmd, ['session', 'list', '--json', '-n', '1'], {
                    cwd,
                    shell: process.platform === 'win32',
                    env: process.env,
                });
            } catch {
                resolve(null);
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c: Buffer) => { buf += c.toString(); });
            proc.on('error', () => resolve(null));
            proc.on('close', () => {
                try {
                    const arr = JSON.parse(buf.replace(ANSI, ''));
                    const id = Array.isArray(arr) && arr[0] && arr[0].sessionId;
                    resolve(typeof id === 'string' ? id : null);
                } catch {
                    resolve(null);
                }
            });
        });
    }

    /**
     * Ask Auggie a one-off question in read-only mode (`--print --ask`) and
     * resolve with the plain-text answer. Used by the prompt enhancer: it never
     * edits files, never touches session memory, and does NOT set `this.proc`
     * so it can run alongside a normal run without tripping isRunning(). Meta
     * lines (Request ID, the lone 🤖 marker) are stripped. Best-effort:
     * resolves to '' on any failure.
     */
    public ask(cwd: string, prompt: string, model?: string): Promise<string> {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get<string>('auggiePath', 'auggie');
            const useShell = process.platform === 'win32';
            const promptArg = useShell ? '"' + prompt.replace(/"/g, '""') + '"' : prompt;
            const args: string[] = [];
            if (model) { args.push('-m', model); }
            args.push('--print', '--ask', promptArg);
            let proc: ChildProcess;
            try {
                proc = spawn(cmd, args, { cwd, shell: useShell, env: process.env });
            } catch {
                resolve('');
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c: Buffer) => { buf += c.toString(); });
            proc.on('error', () => resolve(''));
            proc.on('close', () => {
                const text = buf
                    .replace(ANSI, '')
                    .split(/\r?\n/)
                    .filter(l => !/^\s*Request ID:/i.test(l) && l.trim() !== '🤖')
                    .join('\n')
                    .trim();
                resolve(text);
            });
        });
    }

    /**
     * Run a single task via the Auggie CLI in print mode. Streams stdout as
     * `text` events and resolves when the process exits. Safety is enforced by
     * the caller (no auto-commit/push); this only runs the agent.
     * When `model` is a non-empty Auggie model id it is passed as `-m <id>`.
     * When `resume` is a session id it is passed as `-r <id>` so Auggie
     * continues that conversation instead of starting a fresh, memory-less one.
     */
    public run(
        task: string,
        cwd: string,
        onEvent: (ev: AuggieEvent) => void,
        model?: string,
        resume?: string
    ): Promise<boolean> {
        return new Promise((resolve) => {
            if (this.proc) {
                onEvent({ type: 'error', error: 'An Auggie session is already running. Stop it first.' });
                resolve(false);
                return;
            }

            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get<string>('auggiePath', 'auggie');

            // On Windows we spawn through a shell (to resolve the auggie.cmd /
            // auggie.ps1 shims), which makes cmd.exe re-split the argument list
            // on whitespace. Quote the task so the whole prompt arrives as ONE
            // argument — Auggie's --print expects exactly one. Elsewhere there's
            // no shell, so the raw task is passed through untouched.
            const useShell = process.platform === 'win32';
            const taskArg = useShell ? '"' + task.replace(/"/g, '""') + '"' : task;

            // Build the arg list: resume the prior session (memory) and/or pin a
            // model, then run one-shot in print mode with the quoted task.
            const args: string[] = [];
            if (resume) { args.push('-r', resume); }
            if (model) { args.push('-m', model); }
            args.push('--print', taskArg);

            let proc: ChildProcess;
            try {
                proc = spawn(cmd, args, {
                    cwd,
                    shell: useShell,
                    env: process.env,
                });
            } catch (err: any) {
                onEvent({ type: 'error', error: 'Failed to launch Auggie: ' + (err?.message || String(err)) });
                resolve(false);
                return;
            }

            this.proc = proc;
            let stderrBuf = '';
            // Line buffer so we can drop Auggie's trailing "Request ID: <uuid>"
            // meta line before it reaches the chat. We only emit complete lines;
            // the last partial line is held until a newline arrives (or flush).
            let lineBuf = '';
            const emit = (text: string, flush: boolean) => {
                lineBuf += text;
                let ready: string;
                const nl = lineBuf.lastIndexOf('\n');
                if (flush) { ready = lineBuf; lineBuf = ''; }
                else if (nl >= 0) { ready = lineBuf.slice(0, nl + 1); lineBuf = lineBuf.slice(nl + 1); }
                else { return; }
                const kept = ready
                    .split('\n')
                    .filter(l => !/^\s*Request ID:/i.test(l))
                    .join('\n');
                if (kept) { onEvent({ type: 'text', content: kept }); }
            };

            proc.stdout?.on('data', (chunk: Buffer) => {
                const text = chunk.toString().replace(ANSI, '');
                if (text) { emit(text, false); }
            });

            proc.stderr?.on('data', (chunk: Buffer) => {
                stderrBuf += chunk.toString();
            });

            proc.on('error', (err: any) => {
                const notFound = err && err.code === 'ENOENT';
                const msg = notFound
                    ? 'Auggie CLI not found. Install it with "npm i -g @augmentcode/auggie", then run "auggie login".'
                    : 'Auggie process error: ' + (err?.message || String(err));
                onEvent({ type: 'error', error: msg });
                this.proc = null;
                resolve(false);
            });

            proc.on('close', (code) => {
                this.proc = null;
                emit('', true); // flush any held-back final line (Request ID filtered out)
                if (code !== 0) {
                    const needsLogin = /not logged in|unauthor|please log ?in|auggie login/i.test(stderrBuf);
                    const hint = needsLogin
                        ? ' — run "auggie login" in a terminal first.'
                        : '';
                    const detail = stderrBuf.replace(ANSI, '').trim().slice(0, 500);
                    onEvent({
                        type: 'error',
                        error: 'Auggie exited with code ' + code + hint + (detail ? '\n' + detail : ''),
                    });
                }
                resolve(code === 0);
            });
        });
    }
}
