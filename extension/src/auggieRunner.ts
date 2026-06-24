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
    ): Promise<void> {
        return new Promise((resolve) => {
            if (this.proc) {
                onEvent({ type: 'error', error: 'An Auggie session is already running. Stop it first.' });
                resolve();
                return;
            }

            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get<string>('auggiePath', 'auggie');

            let proc: ChildProcess;
            try {
                proc = spawn(cmd, ['--print', task], {
                    cwd,
                    // Resolve .cmd / .ps1 shims on Windows and PATH lookups everywhere.
                    shell: process.platform === 'win32',
                    env: process.env,
                });
            } catch (err: any) {
                onEvent({ type: 'error', error: 'Failed to launch Auggie: ' + (err?.message || String(err)) });
                resolve();
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
                resolve();
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
                resolve();
            });
        });
    }
}
