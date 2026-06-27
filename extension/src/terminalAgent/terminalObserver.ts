/**
 * AGENT NEO - Terminal Agent Orchestrator: Terminal Observer
 *
 * A rolling, bounded output buffer fed from any source — a Neo-launched
 * process (ProcessRunner events), a tailed log file (logTail.ts), a manual
 * paste, or a best-effort VS Code terminal read. Pure: no `vscode`/`fs` import,
 * so the buffering + dispatch logic is unit-testable in isolation.
 */

export type ObserverSource = 'neo-process' | 'log-file' | 'manual' | 'vscode-terminal';

export interface ObserverChunk {
    chunk: string;
    source: ObserverSource;
}

/** A bounded, append-only text buffer that keeps only the most recent chars. */
export class RollingBuffer {
    private buf = '';

    constructor(private readonly maxChars = 200_000) {}

    append(chunk: string): void {
        if (!chunk) { return; }
        this.buf = (this.buf + chunk).slice(-this.maxChars);
    }

    get text(): string {
        return this.buf;
    }

    get length(): number {
        return this.buf.length;
    }

    lines(): string[] {
        return this.buf.length ? this.buf.split(/\r?\n/) : [];
    }

    /** The last `n` non-empty lines (trimmed), oldest-first. */
    recentLines(n: number): string[] {
        return this.lines()
            .map(l => l.trim())
            .filter(l => l.length > 0)
            .slice(-n);
    }

    clear(): void {
        this.buf = '';
    }
}

/**
 * Given the previously consumed length and the current full content, return
 * only the newly appended slice. If the content shrank (file rotated/
 * truncated) the whole content is treated as new.
 */
export function computeTailDelta(
    previousLength: number,
    fullContent: string,
): { delta: string; newLength: number } {
    if (fullContent.length < previousLength) {
        return { delta: fullContent, newLength: fullContent.length };
    }
    return { delta: fullContent.slice(previousLength), newLength: fullContent.length };
}

export type ObserverListener = (event: ObserverChunk, buffer: RollingBuffer) => void;

/**
 * Collects output from one or more sources into a single rolling buffer and
 * fans new chunks out to subscribers. The active `source` is informational —
 * every source funnels through `ingest`, keeping wiring uniform.
 */
export class TerminalObserver {
    private readonly buffer: RollingBuffer;
    private readonly listeners = new Set<ObserverListener>();
    private active = false;
    public source: ObserverSource;

    constructor(opts: { maxChars?: number; source?: ObserverSource } = {}) {
        this.buffer = new RollingBuffer(opts.maxChars);
        this.source = opts.source ?? 'neo-process';
    }

    start(source?: ObserverSource): void {
        if (source) { this.source = source; }
        this.active = true;
    }

    stop(): void {
        this.active = false;
    }

    isActive(): boolean {
        return this.active;
    }

    /** Push a chunk from the active (or an explicitly named) source. */
    ingest(chunk: string, source: ObserverSource = this.source): void {
        if (!chunk) { return; }
        this.buffer.append(chunk);
        const event: ObserverChunk = { chunk, source };
        for (const l of this.listeners) {
            try { l(event, this.buffer); } catch { /* listener errors never break ingest */ }
        }
    }

    /** Import user-pasted output; normalises CRLF and ensures a trailing newline. */
    importPaste(text: string): void {
        if (!text) { return; }
        const normalised = text.replace(/\r\n/g, '\n');
        this.ingest(normalised.endsWith('\n') ? normalised : normalised + '\n', 'manual');
    }

    snapshot(): string {
        return this.buffer.text;
    }

    recentLines(n: number): string[] {
        return this.buffer.recentLines(n);
    }

    clear(): void {
        this.buffer.clear();
    }

    /** Subscribe to new chunks; returns an unsubscribe function. */
    subscribe(listener: ObserverListener): () => void {
        this.listeners.add(listener);
        return () => { this.listeners.delete(listener); };
    }
}
