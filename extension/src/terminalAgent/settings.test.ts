import { describe, it, expect } from 'vitest';
import {
    readTerminalAgentSettings,
    isOrchestratorEnabled,
    ConfigGetter,
} from './settings';

/** Build a getter over a flat settings map, mirroring WorkspaceConfiguration.get. */
function getterFrom(map: Record<string, unknown>): ConfigGetter {
    return (<T>(key: string, def: T): T =>
        (key in map ? (map[key] as T) : def)) as ConfigGetter;
}

describe('readTerminalAgentSettings', () => {
    it('defaults to disabled with sensible defaults (behavior unchanged)', () => {
        const s = readTerminalAgentSettings(getterFrom({}));
        expect(s.enabled).toBe(false);
        expect(isOrchestratorEnabled(s)).toBe(false);
        expect(s.defaultProvider).toBe('augment-cli');
        expect(s.cliPath).toBe('auggie');
        expect(s.maxTimeoutSeconds).toBe(1800);
        expect(s.captureOutput).toBe(true);
        expect(s.confirmBeforeSendingInput).toBe(true);
        expect(s.observer.enabled).toBe(false);
        expect(s.observer.mode).toBe('neo-process');
    });

    it('enabling the module exposes the orchestrator', () => {
        const s = readTerminalAgentSettings(
            getterFrom({ 'terminalAgent.enabled': true }),
        );
        expect(isOrchestratorEnabled(s)).toBe(true);
    });

    it('observer stays off while the module is disabled, even if its flag is on', () => {
        const s = readTerminalAgentSettings(
            getterFrom({
                'terminalAgent.enabled': false,
                'terminalAgent.observer.enabled': true,
            }),
        );
        expect(s.observer.enabled).toBe(false);
    });

    it('observer activates only when both flags are on', () => {
        const s = readTerminalAgentSettings(
            getterFrom({
                'terminalAgent.enabled': true,
                'terminalAgent.observer.enabled': true,
                'terminalAgent.observer.mode': 'log-file',
            }),
        );
        expect(s.observer.enabled).toBe(true);
        expect(s.observer.mode).toBe('log-file');
    });
});
