"use strict";
/**
 * AGENT NEO - Auggie Runner
 * Runs the Auggie CLI as a local subprocess so it can act as an alternate
 * agent backend. Output is streamed back as normalized events that the chat
 * webview already understands (text / error / finish).
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
exports.AuggieRunner = void 0;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;
class AuggieRunner {
    constructor() {
        this.proc = null;
    }
    isRunning() {
        return this.proc !== null;
    }
    /**
     * Kill the active Auggie process, if any.
     */
    stop() {
        if (this.proc) {
            try {
                this.proc.kill();
            }
            catch { /* already gone */ }
            this.proc = null;
        }
    }
    /**
     * Run a single task via the Auggie CLI in print mode. Streams stdout as
     * `text` events and resolves when the process exits. Safety is enforced by
     * the caller (no auto-commit/push); this only runs the agent.
     */
    run(task, cwd, onEvent) {
        return new Promise((resolve) => {
            if (this.proc) {
                onEvent({ type: 'error', error: 'An Auggie session is already running. Stop it first.' });
                resolve(false);
                return;
            }
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get('auggiePath', 'auggie');
            // On Windows we spawn through a shell (to resolve the auggie.cmd /
            // auggie.ps1 shims), which makes cmd.exe re-split the argument list
            // on whitespace. Quote the task so the whole prompt arrives as ONE
            // argument — Auggie's --print expects exactly one. Elsewhere there's
            // no shell, so the raw task is passed through untouched.
            const useShell = process.platform === 'win32';
            const taskArg = useShell ? '"' + task.replace(/"/g, '""') + '"' : task;
            let proc;
            try {
                proc = (0, child_process_1.spawn)(cmd, ['--print', taskArg], {
                    cwd,
                    shell: useShell,
                    env: process.env,
                });
            }
            catch (err) {
                onEvent({ type: 'error', error: 'Failed to launch Auggie: ' + (err?.message || String(err)) });
                resolve(false);
                return;
            }
            this.proc = proc;
            let stderrBuf = '';
            proc.stdout?.on('data', (chunk) => {
                const text = chunk.toString().replace(ANSI, '');
                if (text) {
                    onEvent({ type: 'text', content: text });
                }
            });
            proc.stderr?.on('data', (chunk) => {
                stderrBuf += chunk.toString();
            });
            proc.on('error', (err) => {
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
exports.AuggieRunner = AuggieRunner;
//# sourceMappingURL=auggieRunner.js.map