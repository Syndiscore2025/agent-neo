import { defineConfig } from 'vitest/config';

/**
 * Dev-only test harness for the Terminal Agent Orchestrator's pure logic
 * (providers, prompt builder, settings reader, parsers, suggestion/safety).
 * These modules deliberately avoid importing `vscode`, so they run here with
 * no extension host. UI/process-spawn glue is excluded.
 */
export default defineConfig({
    test: {
        include: ['src/**/*.test.ts'],
        environment: 'node',
    },
});
