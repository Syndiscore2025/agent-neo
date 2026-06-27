"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Settings reader
 *
 * Reads the agentNeo.terminalAgent.* configuration into a typed object. The
 * core reader takes a generic getter so it stays unit-testable without the
 * `vscode` module; the extension passes a WorkspaceConfiguration-backed getter.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.readTerminalAgentSettings = readTerminalAgentSettings;
exports.isOrchestratorEnabled = isOrchestratorEnabled;
/** Read settings from any getter shaped like WorkspaceConfiguration.get. */
function readTerminalAgentSettings(get) {
    const enabled = get('terminalAgent.enabled', false);
    const observerEnabledRaw = get('terminalAgent.observer.enabled', false);
    return {
        enabled,
        defaultProvider: get('terminalAgent.defaultProvider', 'augment-cli'),
        cliPath: get('terminalAgent.cliPath', 'auggie'),
        defaultWorkingDir: get('terminalAgent.defaultWorkingDir', ''),
        promptTemplate: get('terminalAgent.promptTemplate', ''),
        maxTimeoutSeconds: get('terminalAgent.maxTimeoutSeconds', 1800),
        captureOutput: get('terminalAgent.captureOutput', true),
        autoSaveSummaries: get('terminalAgent.autoSaveSummaries', true),
        confirmBeforeSendingInput: get('terminalAgent.confirmBeforeSendingInput', true),
        observer: {
            // Observer is only meaningful when the module itself is enabled.
            enabled: enabled && observerEnabledRaw,
            mode: get('terminalAgent.observer.mode', 'neo-process'),
            logFilePath: get('terminalAgent.observer.logFilePath', ''),
        },
    };
}
/**
 * Whether orchestrator actions (chat button, panels, commands) should be
 * exposed. The single source of truth for "is the module on".
 */
function isOrchestratorEnabled(settings) {
    return settings.enabled === true;
}
//# sourceMappingURL=settings.js.map