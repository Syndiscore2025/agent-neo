import { describe, it, expect } from 'vitest';
import { EventEmitter } from 'events';
import { ProcessRunner, RunnerEvent } from './processRunner';
import { BuiltCommand, ProviderConfig } from './providers/types';

/** Minimal fake ChildProcess: EventEmitter + stdout/stderr + kill(). */
class FakeProc extends EventEmitter {
    stdout = new EventEmitter();
    stderr = new EventEmitter();
    pid = 4242;
    killed = false;
    closeCode: number | null = null;
    kill(): boolean {
        this.killed = true;
        queueMicrotask(() => this.emit('close', this.closeCode));
        return true;
    }
}

const built: BuiltCommand = { cmd: 'auggie', args: ['--print', 'x'], useShell: false };
const config: ProviderConfig = { cliPath: 'auggie', workingDir: '/work', maxTimeoutSeconds: 0, captureOutput: true };

describe('ProcessRunner', () => {
    it('streams stdout/stderr, captures output, finishes ok on code 0', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const events: RunnerEvent[] = [];
        const p = runner.run(built, config, e => events.push(e));
        fake.stdout.emit('data', Buffer.from('hello '));
        fake.stderr.emit('data', Buffer.from('warn'));
        fake.emit('close', 0);
        const res = await p;
        expect(res.ok).toBe(true);
        expect(res.code).toBe(0);
        expect(res.output).toContain('hello');
        expect(res.output).toContain('warn');
        expect(events.some(e => e.type === 'text')).toBe(true);
        expect(events.some(e => e.type === 'stderr')).toBe(true);
        expect(events.some(e => e.type === 'finish')).toBe(true);
    });

    it('strips ANSI from captured output', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const p = runner.run(built, config);
        fake.stdout.emit('data', Buffer.from('\u001b[32mhi\u001b[0m'));
        fake.emit('close', 0);
        const res = await p;
        expect(res.output).toContain('hi');
        expect(res.output).not.toContain('\u001b[');
    });

    it('does not retain output when captureOutput is false', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const events: RunnerEvent[] = [];
        const p = runner.run(built, { ...config, captureOutput: false }, e => events.push(e));
        fake.stdout.emit('data', Buffer.from('secretish'));
        fake.emit('close', 0);
        const res = await p;
        expect(res.output).toBe('');
        expect(events.some(e => e.type === 'text')).toBe(true);
    });

    it('handles cancellation', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const events: RunnerEvent[] = [];
        const p = runner.run(built, config, e => events.push(e));
        runner.stop();
        const res = await p;
        expect(res.cancelled).toBe(true);
        expect(res.ok).toBe(false);
        expect(events.some(e => e.type === 'cancelled')).toBe(true);
        expect(fake.killed).toBe(true);
    });

    it('handles timeout', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const events: RunnerEvent[] = [];
        const res = await runner.run(built, { ...config, maxTimeoutSeconds: 0.05 }, e => events.push(e));
        expect(res.timedOut).toBe(true);
        expect(res.ok).toBe(false);
        expect(events.some(e => e.type === 'timeout')).toBe(true);
    });

    it('reports a non-zero exit as not-ok', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const p = runner.run(built, config);
        fake.emit('close', 2);
        const res = await p;
        expect(res.ok).toBe(false);
        expect(res.code).toBe(2);
    });

    it('surfaces ENOENT as a clear not-found error', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const events: RunnerEvent[] = [];
        const p = runner.run(built, config, e => events.push(e));
        fake.emit('error', Object.assign(new Error('boom'), { code: 'ENOENT' }));
        const res = await p;
        expect(res.ok).toBe(false);
        expect(events.find(e => e.type === 'error')?.error).toContain('not found');
    });

    it('refuses to start a second concurrent run', async () => {
        const fake = new FakeProc();
        const runner = new ProcessRunner(() => fake as any);
        const p1 = runner.run(built, config);
        const r2 = await runner.run(built, config);
        expect(r2.ok).toBe(false);
        fake.emit('close', 0);
        await p1;
        expect(runner.isRunning()).toBe(false);
    });
});
