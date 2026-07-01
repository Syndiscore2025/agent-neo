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
     * List the models Auggie offers via `auggie model list`, parsed into
     * { id, label } pairs (id is the bracketed short name, e.g. "opus4.8").
     * Best-effort: resolves to [] if the CLI is missing, not logged in, or the
     * output can't be parsed.
     */
    listModels() {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get('auggiePath', 'auggie');
            let proc;
            try {
                proc = (0, child_process_1.spawn)(cmd, ['model', 'list'], {
                    shell: process.platform === 'win32',
                    env: process.env,
                });
            }
            catch {
                resolve([]);
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c) => { buf += c.toString(); });
            proc.on('error', () => resolve([]));
            proc.on('close', () => {
                const out = [];
                for (const raw of buf.replace(ANSI, '').split(/\r?\n/)) {
                    const m = raw.match(/^\s*-\s*(.+?)\s*\[([^\]]+)\]\s*$/);
                    if (m) {
                        out.push({ label: m[1].trim(), id: m[2].trim() });
                    }
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
    getLatestSessionId(cwd) {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get('auggiePath', 'auggie');
            let proc;
            try {
                proc = (0, child_process_1.spawn)(cmd, ['session', 'list', '--json', '-n', '1'], {
                    cwd,
                    shell: process.platform === 'win32',
                    env: process.env,
                });
            }
            catch {
                resolve(null);
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c) => { buf += c.toString(); });
            proc.on('error', () => resolve(null));
            proc.on('close', () => {
                try {
                    const arr = JSON.parse(buf.replace(ANSI, ''));
                    const id = Array.isArray(arr) && arr[0] && arr[0].sessionId;
                    resolve(typeof id === 'string' ? id : null);
                }
                catch {
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
    ask(cwd, prompt, model) {
        return new Promise((resolve) => {
            const cmd = vscode.workspace
                .getConfiguration('agentNeo')
                .get('auggiePath', 'auggie');
            const useShell = process.platform === 'win32';
            const promptArg = useShell ? '"' + prompt.replace(/"/g, '""') + '"' : prompt;
            const args = [];
            if (model) {
                args.push('-m', model);
            }
            args.push('--print', '--ask', promptArg);
            let proc;
            try {
                proc = (0, child_process_1.spawn)(cmd, args, { cwd, shell: useShell, env: process.env });
            }
            catch {
                resolve('');
                return;
            }
            let buf = '';
            proc.stdout?.on('data', (c) => { buf += c.toString(); });
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
    run(task, cwd, onEvent, model, resume) {
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
            // Build the arg list: resume the prior session (memory) and/or pin a
            // model, then run one-shot in print mode with the quoted task.
            const args = [];
            if (resume) {
                args.push('-r', resume);
            }
            if (model) {
                args.push('-m', model);
            }
            args.push('--print', taskArg);
            let proc;
            try {
                proc = (0, child_process_1.spawn)(cmd, args, {
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
            // Line buffer so we can drop Auggie's trailing "Request ID: <uuid>"
            // meta line before it reaches the chat. We only emit complete lines;
            // the last partial line is held until a newline arrives (or flush).
            let lineBuf = '';
            const emit = (text, flush) => {
                lineBuf += text;
                let ready;
                const nl = lineBuf.lastIndexOf('\n');
                if (flush) {
                    ready = lineBuf;
                    lineBuf = '';
                }
                else if (nl >= 0) {
                    ready = lineBuf.slice(0, nl + 1);
                    lineBuf = lineBuf.slice(nl + 1);
                }
                else {
                    return;
                }
                const kept = ready
                    .split('\n')
                    .filter(l => !/^\s*Request ID:/i.test(l))
                    .join('\n');
                if (kept) {
                    onEvent({ type: 'text', content: kept });
                }
            };
            proc.stdout?.on('data', (chunk) => {
                const text = chunk.toString().replace(ANSI, '');
                if (text) {
                    emit(text, false);
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
exports.AuggieRunner = AuggieRunner;
//# sourceMappingURL=auggieRunner.js.map