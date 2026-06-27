import { describe, it, expect, vi } from 'vitest';
import {
    RollingBuffer,
    computeTailDelta,
    TerminalObserver,
} from './terminalObserver';

describe('RollingBuffer', () => {
    it('appends and exposes text + length', () => {
        const b = new RollingBuffer();
        b.append('hello ');
        b.append('world');
        expect(b.text).toBe('hello world');
        expect(b.length).toBe(11);
    });

    it('bounds to the most recent maxChars', () => {
        const b = new RollingBuffer(5);
        b.append('abcdefgh');
        expect(b.text).toBe('defgh');
    });

    it('returns recent non-empty lines only', () => {
        const b = new RollingBuffer();
        b.append('one\n\n two \nthree\n');
        expect(b.recentLines(2)).toEqual(['two', 'three']);
    });

    it('clears the buffer', () => {
        const b = new RollingBuffer();
        b.append('data');
        b.clear();
        expect(b.text).toBe('');
        expect(b.lines()).toEqual([]);
    });
});

describe('computeTailDelta', () => {
    it('returns only the appended slice when content grows', () => {
        expect(computeTailDelta(3, 'abcdef')).toEqual({ delta: 'def', newLength: 6 });
    });

    it('returns empty when nothing was appended', () => {
        expect(computeTailDelta(6, 'abcdef')).toEqual({ delta: '', newLength: 6 });
    });

    it('treats a shrunk file (rotation) as all-new', () => {
        expect(computeTailDelta(10, 'fresh')).toEqual({ delta: 'fresh', newLength: 5 });
    });
});

describe('TerminalObserver', () => {
    it('ingests chunks into the buffer and notifies subscribers', () => {
        const obs = new TerminalObserver();
        const events: string[] = [];
        obs.subscribe(e => events.push(`${e.source}:${e.chunk}`));
        obs.start('log-file');
        obs.ingest('line one\n');
        expect(obs.snapshot()).toBe('line one\n');
        expect(events).toEqual(['log-file:line one\n']);
    });

    it('normalises pasted text and tags it as manual', () => {
        const obs = new TerminalObserver();
        const sources: string[] = [];
        obs.subscribe(e => sources.push(e.source));
        obs.importPaste('a\r\nb');
        expect(obs.snapshot()).toBe('a\nb\n');
        expect(sources).toEqual(['manual']);
    });

    it('ignores empty chunks', () => {
        const obs = new TerminalObserver();
        const cb = vi.fn();
        obs.subscribe(cb);
        obs.ingest('');
        expect(cb).not.toHaveBeenCalled();
        expect(obs.snapshot()).toBe('');
    });

    it('unsubscribe stops further notifications', () => {
        const obs = new TerminalObserver();
        const cb = vi.fn();
        const off = obs.subscribe(cb);
        obs.ingest('x');
        off();
        obs.ingest('y');
        expect(cb).toHaveBeenCalledTimes(1);
    });

    it('a throwing listener never breaks ingest', () => {
        const obs = new TerminalObserver();
        obs.subscribe(() => { throw new Error('boom'); });
        expect(() => obs.ingest('safe')).not.toThrow();
        expect(obs.snapshot()).toBe('safe');
    });

    it('tracks active state via start/stop', () => {
        const obs = new TerminalObserver();
        expect(obs.isActive()).toBe(false);
        obs.start();
        expect(obs.isActive()).toBe(true);
        obs.stop();
        expect(obs.isActive()).toBe(false);
    });
});
