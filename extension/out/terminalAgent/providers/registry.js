"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.ProviderRegistry = void 0;
exports.getProviderRegistry = getProviderRegistry;
exports.resetProviderRegistry = resetProviderRegistry;
const augmentCli_1 = require("./augmentCli");
class ProviderRegistry {
    constructor() {
        this.providers = new Map();
    }
    register(provider) {
        this.providers.set(provider.id, provider);
    }
    get(id) {
        return this.providers.get(id);
    }
    has(id) {
        return this.providers.has(id);
    }
    list() {
        return [...this.providers.values()];
    }
    ids() {
        return [...this.providers.keys()];
    }
}
exports.ProviderRegistry = ProviderRegistry;
let _registry = null;
/** Singleton registry, lazily seeded with the built-in providers. */
function getProviderRegistry() {
    if (!_registry) {
        _registry = new ProviderRegistry();
        _registry.register(new augmentCli_1.AugmentCLIProvider());
    }
    return _registry;
}
/** Test hook: drop the singleton so the next get rebuilds it. */
function resetProviderRegistry() {
    _registry = null;
}
//# sourceMappingURL=registry.js.map