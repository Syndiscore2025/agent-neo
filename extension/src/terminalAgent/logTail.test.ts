import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { LogFileTailer } from './logTail';

describe('LogFileTailer', () => {
    it('emits only newly appended content across polls', () => {
        let content = 'first\n';
        const deltas: string[] = [];
        const tailer = new LogFileTailer(() => content, d => deltas.push(d));

        tailer.poll();
        content += 'second\n';
        tailer.poll();
        tailer.poll();
        content += 'third\n';
        tailer.poll();

        expect(deltas).toEqual(['first\n', 'second\n', 'third\n']);
    });

    it('re-reads from the start when the file rotates/shrinks', () => {
        let content = 'aaaa';
        const deltas: string[] = [];
        const tailer = new LogFileTailer(() => content, d => deltas.push(d));
        tailer.poll();
        content = 'bb';
        tailer.poll();
        expect(deltas).toEqual(['aaaa', 'bb']);
    });

    it('swallows read errors and recovers on a later poll', () => {
        let fail = true;
        let content = '';
        const deltas: string[] = [];
        const tailer = new LogFileTailer(
            () => { if (fail) { throw new Error('missing'); } return content; },
            d => deltas.push(d),
        );
        tailer.poll();
        expect(deltas).toEqual([]);
        fail = false;
        content = 'back\n';
        tailer.poll();
        expect(deltas).toEqual(['back\n']);
    });
});

describe('LogFileTailer interval', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('start() polls immediately and on each interval; stop() halts', () => {
        let content = 'a';
        const deltas: string[] = [];
        const tailer = new LogFileTailer(() => content, d => deltas.push(d));

        tailer.start(1000);
        expect(deltas).toEqual(['a']);
        content = 'ab';
        vi.advanceTimersByTime(1000);
        expect(deltas).toEqual(['a', 'b']);

        tailer.stop();
        content = 'abc';
        vi.advanceTimersByTime(5000);
        expect(deltas).toEqual(['a', 'b']);
        expect(tailer.isRunning()).toBe(false);
    });

    it('start() is idempotent', () => {
        const tailer = new LogFileTailer(() => '', () => {});
        tailer.start(1000);
        tailer.start(1000);
        expect(tailer.isRunning()).toBe(true);
        tailer.stop();
    });
});
