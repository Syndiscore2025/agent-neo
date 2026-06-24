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
     * Run a single task via the Auggie CLI in print mode. Streams stdout as
     * `text` events and resolves when the process exits. Safety is enforced by
     * the caller (no auto-commit/push); this only runs the agent.
     */
    public run(
        task: string,
        cwd: string,
        onEvent: (ev: AuggieEvent) => void
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

            let proc: ChildProcess;
            try {
                proc = spawn(cmd, ['--print', taskArg], {
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

            proc.stdout?.on('data', (chunk: Buffer) => {
                const text = chunk.toString().replace(ANSI, '');
                if (text) { onEvent({ type: 'text', content: text }); }
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
