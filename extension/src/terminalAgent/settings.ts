/**
 * AGENT NEO - Terminal Agent Orchestrator: Settings reader
 *
 * Reads the agentNeo.terminalAgent.* configuration into a typed object. The
 * core reader takes a generic getter so it stays unit-testable without the
 * `vscode` module; the extension passes a WorkspaceConfiguration-backed getter.
 */

export type ConfigGetter = <T>(key: string, defaultValue: T) => T;

export interface ObserverSettings {
    enabled: boolean;
    mode: 'neo-process' | 'vscode-terminal' | 'log-file' | 'manual';
    logFilePath: string;
}

export interface TerminalAgentSettings {
    enabled: boolean;
    defaultProvider: string;
    cliPath: string;
    defaultWorkingDir: string;
    promptTemplate: string;
    maxTimeoutSeconds: number;
    captureOutput: boolean;
    autoSaveSummaries: boolean;
    confirmBeforeSendingInput: boolean;
    observer: ObserverSettings;
}

/** Read settings from any getter shaped like WorkspaceConfiguration.get. */
export function readTerminalAgentSettings(get: ConfigGetter): TerminalAgentSettings {
    const enabled = get<boolean>('terminalAgent.enabled', false);
    const observerEnabledRaw = get<boolean>('terminalAgent.observer.enabled', false);
    return {
        enabled,
        defaultProvider: get<string>('terminalAgent.defaultProvider', 'augment-cli'),
        cliPath: get<string>('terminalAgent.cliPath', 'auggie'),
        defaultWorkingDir: get<string>('terminalAgent.defaultWorkingDir', ''),
        promptTemplate: get<string>('terminalAgent.promptTemplate', ''),
        maxTimeoutSeconds: get<number>('terminalAgent.maxTimeoutSeconds', 1800),
        captureOutput: get<boolean>('terminalAgent.captureOutput', true),
        autoSaveSummaries: get<boolean>('terminalAgent.autoSaveSummaries', true),
        confirmBeforeSendingInput: get<boolean>('terminalAgent.confirmBeforeSendingInput', true),
        observer: {
            // Observer is only meaningful when the module itself is enabled.
            enabled: enabled && observerEnabledRaw,
            mode: get<ObserverSettings['mode']>('terminalAgent.observer.mode', 'neo-process'),
            logFilePath: get<string>('terminalAgent.observer.logFilePath', ''),
        },
    };
}

/**
 * Whether orchestrator actions (chat button, panels, commands) should be
 * exposed. The single source of truth for "is the module on".
 */
export function isOrchestratorEnabled(settings: TerminalAgentSettings): boolean {
    return settings.enabled === true;
}
