"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Provider types
 *
 * Provider-agnostic contract. Neo talks ONLY to TerminalAgentProvider; every
 * CLI-specific assumption (command shape, output parsing, completion markers)
 * lives inside a concrete adapter (e.g. AugmentCLIProvider).
 *
 * This file is intentionally free of any `vscode` import so the pure logic can
 * be unit-tested under vitest without the extension host.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ANSI_RE = void 0;
exports.stripAnsi = stripAnsi;
/** Strip ANSI escape sequences — shared by adapters. */
exports.ANSI_RE = /\x1b\[[0-9;]*[A-Za-z]/g;
function stripAnsi(s) {
    return s.replace(exports.ANSI_RE, '');
}
//# sourceMappingURL=types.js.map