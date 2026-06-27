import { describe, it, expect, beforeEach } from 'vitest';
import { AugmentCLIProvider } from './augmentCli';
import {
    getProviderRegistry,
    resetProviderRegistry,
    ProviderRegistry,
} from './registry';
import { ProviderConfig } from './types';

const baseConfig: ProviderConfig = {
    cliPath: 'auggie',
    workingDir: '/work',
    maxTimeoutSeconds: 60,
    captureOutput: true,
};

describe('AugmentCLIProvider.buildCommand', () => {
    it('builds an `--print` command with the prompt as one argument', () => {
        const p = new AugmentCLIProvider();
        const built = p.buildCommand(baseConfig, 'do the thing');
        expect(built.args[0]).toBe('--print');
        // The prompt is the final argument (quoted on win32, raw elsewhere).
        expect(built.args[built.args.length - 1]).toContain('do the thing');
        expect(built.args.length).toBe(2);
    });

    it('honours a custom cliPath, falling back to the executable name', () => {
        const p = new AugmentCLIProvider();
        expect(p.buildCommand({ ...baseConfig, cliPath: '/opt/auggie' }, 'x').cmd).toBe('/opt/auggie');
        expect(p.buildCommand({ ...baseConfig, cliPath: '' }, 'x').cmd).toBe(p.executableName);
    });
});

describe('AugmentCLIProvider parsing (provider-isolated)', () => {
    const p = new AugmentCLIProvider();

    it('detects milestones from progress lines', () => {
        const ms = p.detectMilestones('Creating file a.ts\nrandom chatter\nRunning tests');
        const labels = ms.map(m => m.label);
        expect(labels).toContain('creating');
        expect(labels).toContain('running');
    });

    it('detects error-looking lines', () => {
        const errs = p.detectErrors('all good\nError: boom\nENOENT: missing');
        expect(errs.length).toBe(2);
    });

    it('detects completion markers', () => {
        expect(p.detectCompletion('... Summary: files changed: 2')).toBe(true);
        expect(p.detectCompletion('still working')).toBe(false);
    });

    it('parseOutput strips ANSI and aggregates signals', () => {
        const raw = '\u001b[32mCreated app.ts\u001b[0m\nError: nope\nNext steps: review';
        const parsed = p.parseOutput(raw);
        expect(parsed.text).not.toContain('\u001b[');
        expect(parsed.milestones.length).toBeGreaterThan(0);
        expect(parsed.errors.length).toBeGreaterThan(0);
        expect(parsed.completed).toBe(true);
    });
});

describe('ProviderRegistry', () => {
    beforeEach(() => resetProviderRegistry());

    it('seeds the Augment CLI provider by default', () => {
        const reg = getProviderRegistry();
        expect(reg.has('augment-cli')).toBe(true);
        expect(reg.get('augment-cli')?.displayName).toBe('Augment CLI');
    });

    it('supports registering additional providers', () => {
        const reg = new ProviderRegistry();
        reg.register({
            id: 'mock', displayName: 'Mock', executableName: 'mock',
            supportsStreaming: true, supportsInteractiveInput: false,
            supportsTerminalObservation: false,
            buildCommand: () => ({ cmd: 'mock', args: [], useShell: false }),
            parseOutput: () => ({ text: '', milestones: [], errors: [], completed: false }),
            detectMilestones: () => [], detectErrors: () => [], detectCompletion: () => false,
        });
        expect(reg.ids()).toContain('mock');
        expect(reg.list().length).toBe(1);
    });
});
