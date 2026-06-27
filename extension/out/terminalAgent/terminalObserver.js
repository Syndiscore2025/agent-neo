"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Terminal Observer
 *
 * A rolling, bounded output buffer fed from any source — a Neo-launched
 * process (ProcessRunner events), a tailed log file (logTail.ts), a manual
 * paste, or a best-effort VS Code terminal read. Pure: no `vscode`/`fs` import,
 * so the buffering + dispatch logic is unit-testable in isolation.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.TerminalObserver = exports.RollingBuffer = void 0;
exports.computeTailDelta = computeTailDelta;
/** A bounded, append-only text buffer that keeps only the most recent chars. */
class RollingBuffer {
    constructor(maxChars = 200000) {
        this.maxChars = maxChars;
        this.buf = '';
    }
    append(chunk) {
        if (!chunk) {
            return;
        }
        this.buf = (this.buf + chunk).slice(-this.maxChars);
    }
    get text() {
        return this.buf;
    }
    get length() {
        return this.buf.length;
    }
    lines() {
        return this.buf.length ? this.buf.split(/\r?\n/) : [];
    }
    /** The last `n` non-empty lines (trimmed), oldest-first. */
    recentLines(n) {
        return this.lines()
            .map(l => l.trim())
            .filter(l => l.length > 0)
            .slice(-n);
    }
    clear() {
        this.buf = '';
    }
}
exports.RollingBuffer = RollingBuffer;
/**
 * Given the previously consumed length and the current full content, return
 * only the newly appended slice. If the content shrank (file rotated/
 * truncated) the whole content is treated as new.
 */
function computeTailDelta(previousLength, fullContent) {
    if (fullContent.length < previousLength) {
        return { delta: fullContent, newLength: fullContent.length };
    }
    return { delta: fullContent.slice(previousLength), newLength: fullContent.length };
}
/**
 * Collects output from one or more sources into a single rolling buffer and
 * fans new chunks out to subscribers. The active `source` is informational —
 * every source funnels through `ingest`, keeping wiring uniform.
 */
class TerminalObserver {
    constructor(opts = {}) {
        this.listeners = new Set();
        this.active = false;
        this.buffer = new RollingBuffer(opts.maxChars);
        this.source = opts.source ?? 'neo-process';
    }
    start(source) {
        if (source) {
            this.source = source;
        }
        this.active = true;
    }
    stop() {
        this.active = false;
    }
    isActive() {
        return this.active;
    }
    /** Push a chunk from the active (or an explicitly named) source. */
    ingest(chunk, source = this.source) {
        if (!chunk) {
            return;
        }
        this.buffer.append(chunk);
        const event = { chunk, source };
        for (const l of this.listeners) {
            try {
                l(event, this.buffer);
            }
            catch { /* listener errors never break ingest */ }
        }
    }
    /** Import user-pasted output; normalises CRLF and ensures a trailing newline. */
    importPaste(text) {
        if (!text) {
            return;
        }
        const normalised = text.replace(/\r\n/g, '\n');
        this.ingest(normalised.endsWith('\n') ? normalised : normalised + '\n', 'manual');
    }
    snapshot() {
        return this.buffer.text;
    }
    recentLines(n) {
        return this.buffer.recentLines(n);
    }
    clear() {
        this.buffer.clear();
    }
    /** Subscribe to new chunks; returns an unsubscribe function. */
    subscribe(listener) {
        this.listeners.add(listener);
        return () => { this.listeners.delete(listener); };
    }
}
exports.TerminalObserver = TerminalObserver;
//# sourceMappingURL=terminalObserver.js.map