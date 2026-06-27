/**
 * AGENT NEO - Terminal Agent Orchestrator: Provider registry
 *
 * Registration + lookup for terminal-agent providers. Augment CLI is seeded as
 * the first adapter; future providers (Claude Code, Codex, Gemini, Roo, custom
 * local agents) register the same way. Mirrors the backend's get_*_registry /
 * reset_* singleton pattern so tests can reset cleanly.
 *
 * No `vscode` import.
 */

import { TerminalAgentProvider } from './types';
import { AugmentCLIProvider } from './augmentCli';

export class ProviderRegistry {
    private readonly providers = new Map<string, TerminalAgentProvider>();

    register(provider: TerminalAgentProvider): void {
        this.providers.set(provider.id, provider);
    }

    get(id: string): TerminalAgentProvider | undefined {
        return this.providers.get(id);
    }

    has(id: string): boolean {
        return this.providers.has(id);
    }

    list(): TerminalAgentProvider[] {
        return [...this.providers.values()];
    }

    ids(): string[] {
        return [...this.providers.keys()];
    }
}

let _registry: ProviderRegistry | null = null;

/** Singleton registry, lazily seeded with the built-in providers. */
export function getProviderRegistry(): ProviderRegistry {
    if (!_registry) {
        _registry = new ProviderRegistry();
        _registry.register(new AugmentCLIProvider());
    }
    return _registry;
}

/** Test hook: drop the singleton so the next get rebuilds it. */
export function resetProviderRegistry(): void {
    _registry = null;
}
