import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EventEmitter } from 'events';
import { OrchestratorController, OrchestratorDeps, PostRunStatusLite } from './orchestratorController';
import { ProcessRunner } from './processRunner';
import { SessionHistory, KeyValueStore } from './history';
import { TerminalAgentSettings } from './settings';
import { RunContext } from './providers/types';
import { resetProviderRegistry } from './providers/registry';

class FakeProc extends EventEmitter {
    stdout = new EventEmitter();
    stderr = new EventEmitter();
    pid = 1;
    kill() { queueMicrotask(() => this.emit('close', 0)); return true; }
}
/** Spawn that emits `output` then closes with `code`. */
function autoSpawn(output: string, code = 0) {
    return () => {
        const fake = new FakeProc();
        queueMicrotask(() => {
            if (output) { fake.stdout.emit('data', Buffer.from(output)); }
            fake.emit('close', code);
        });
        return fake as any;
    };
}
class MemStore implements KeyValueStore {
    private m = new Map<string, unknown>();
    get<T>(k: string) { return this.m.get(k) as T | undefined; }
    async update(k: string, v: unknown) { this.m.set(k, v); }
}

const settings: TerminalAgentSettings = {
    enabled: true, defaultProvider: 'augment-cli', cliPath: 'auggie',
    defaultWorkingDir: '', promptTemplate: '', maxTimeoutSeconds: 0,
    captureOutput: true, autoSaveSummaries: true, confirmBeforeSendingInput: true,
    observer: { enabled: false, mode: 'neo-process', logFilePath: '' },
};
const context: RunContext = {
    repoPath: '/work', currentBranch: 'main', gitStatus: ' M a.ts',
    changedFiles: ['a.ts'], recentCommits: ['abc fix'], openFiles: ['a.ts'],
    providerName: 'Augment CLI', dateTime: '2026-01-01T00:00:00Z',
};
const postRun: PostRunStatusLite = {
    branch: 'main', changedFiles: ['a.ts', 'b.ts'], stagedFiles: [], unstagedFiles: ['a.ts', 'b.ts'],
};

function makeDeps(over: Partial<OrchestratorDeps> = {}, spawnOut = 'done\n', code = 0): {
    deps: OrchestratorDeps; posts: any[]; history: SessionHistory;
} {
    const posts: any[] = [];
    const history = new SessionHistory(new MemStore());
    const deps: OrchestratorDeps = {
        post: m => posts.push(m),
        settings,
        history,
        gatherContext: vi.fn(async () => context),
        getPostRunStatus: vi.fn(async () => postRun),
        reviewPrompt: vi.fn(async (p: string) => p),
        runner: new ProcessRunner(autoSpawn(spawnOut, code)),
        ...over,
    };
    return { deps, posts, history };
}

describe('OrchestratorController', () => {
    beforeEach(() => resetProviderRegistry());

    it('runs end to end and persists a completed session', async () => {
        const { deps, posts, history } = makeDeps();
        const ctrl = new OrchestratorController(deps);
        const session = await ctrl.start('Add health endpoint', '/work');
        expect(session?.status).toBe('completed');
        expect(session?.changed_files).toEqual(['a.ts', 'b.ts']);
        expect(session?.current_branch_current).toBe('main');
        expect(history.list().length).toBe(1);
        const types = posts.map(p => p.type);
        expect(types).toContain('streamRunStart');
        expect(types).toContain('streamRunDone');
        const finish = posts.find(p => p.event?.type === 'finish');
        expect(finish.event.success).toBe(true);
    });

    it('cancels cleanly at review without starting a run', async () => {
        const { deps, posts, history } = makeDeps({ reviewPrompt: vi.fn(async () => undefined) });
        const ctrl = new OrchestratorController(deps);
        const session = await ctrl.start('task', '/work');
        expect(session).toBeNull();
        expect(posts.map(p => p.type)).not.toContain('streamRunStart');
        expect(history.list().length).toBe(0);
    });

    it('uses the edited prompt and preserves the request in the generated prompt', async () => {
        const { deps } = makeDeps({ reviewPrompt: vi.fn(async () => 'EDITED PROMPT BODY') });
        const ctrl = new OrchestratorController(deps);
        const session = await ctrl.start('Implement X', '/work');
        expect(session?.edited_prompt).toBe('EDITED PROMPT BODY');
        expect(session?.generated_prompt).toContain('Implement X');
    });

    it('marks a non-zero exit as failed', async () => {
        const { deps, posts } = makeDeps({}, 'err\n', 2);
        const ctrl = new OrchestratorController(deps);
        const session = await ctrl.start('task', '/work');
        expect(session?.status).toBe('failed');
        expect(posts.find(p => p.event?.type === 'finish').event.success).toBe(false);
    });

    it('never persists secrets from streamed output', async () => {
        const { deps, history } = makeDeps({}, 'export OPENAI_API_KEY=sk-LEAK-XYZ\n');
        const ctrl = new OrchestratorController(deps);
        await ctrl.start('task', '/work');
        expect(JSON.stringify(history.list())).not.toContain('sk-LEAK-XYZ');
    });

    it('analyses output: test results, claim verification, and suggestions', async () => {
        const out = 'created src/feature.ts\nTests: 1 failed, 2 passed\n';
        const { deps, posts } = makeDeps({
            getPostRunStatus: vi.fn(async () => ({
                branch: 'main', changedFiles: ['src/feature.ts'], stagedFiles: [],
                unstagedFiles: ['src/feature.ts'], untracked: [], commits: [],
            })),
        }, out, 0);
        const ctrl = new OrchestratorController(deps);
        const s = await ctrl.start('add feature', '/work');
        expect(s?.tests_detected).toBe(true);
        expect(s?.tests_passed).toBe(2);
        expect(s?.tests_failed).toBe(1);
        expect(s?.suggestions.map(x => x.id)).toContain('fix-tests');
        const finish = posts.find(p => p.event?.type === 'finish');
        expect(finish.event.verification.verified).toEqual(['src/feature.ts']);
    });

    it('redacts secrets from streamed display output', async () => {
        const { deps, posts } = makeDeps({}, 'token printed: sk-abcdef0123456789\n');
        const ctrl = new OrchestratorController(deps);
        await ctrl.start('task', '/work');
        const streamed = posts
            .filter(p => p.event?.type === 'text')
            .map(p => p.event.content)
            .join('');
        expect(streamed).not.toContain('sk-abcdef0123456789');
        expect(streamed).toContain('[REDACTED]');
    });
});
