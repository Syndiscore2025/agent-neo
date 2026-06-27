/**
 * AGENT NEO - Terminal Agent Orchestrator: Log-file tailer
 *
 * Incrementally tails a growing log file, emitting only newly appended text.
 * The content reader is injectable so the tailing/delta logic is unit-testable
 * without touching the real filesystem; `fileReader` wires it to fs for the
 * extension. Rotation/truncation is handled via computeTailDelta.
 */

import * as fs from 'fs';
import { computeTailDelta } from './terminalObserver';

/** Returns the full current content of the source, or throws if unavailable. */
export type ContentReader = () => string;

export class LogFileTailer {
    private lastLength = 0;
    private timer: ReturnType<typeof setInterval> | null = null;

    constructor(
        private readonly read: ContentReader,
        private readonly onDelta: (delta: string) => void,
    ) {}

    /**
     * Read the source once and emit only the part appended since the last poll.
     * Read failures (file missing/locked) are swallowed so polling can recover
     * once the file appears.
     */
    poll(): void {
        let content: string;
        try {
            content = this.read();
        } catch {
            return;
        }
        const { delta, newLength } = computeTailDelta(this.lastLength, content);
        this.lastLength = newLength;
        if (delta) { this.onDelta(delta); }
    }

    /** Begin polling on an interval. Idempotent. */
    start(intervalMs = 1000): void {
        if (this.timer) { return; }
        this.poll();
        this.timer = setInterval(() => this.poll(), intervalMs);
    }

    stop(): void {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    isRunning(): boolean {
        return this.timer !== null;
    }
}

/** A ContentReader backed by the real filesystem. */
export function fileReader(path: string): ContentReader {
    return () => fs.readFileSync(path, 'utf8');
}
