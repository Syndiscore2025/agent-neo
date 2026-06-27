import { describe, it, expect, beforeEach } from 'vitest';
import { SessionHistory, KeyValueStore, toSummary } from './history';
import { createSession, appendOutput, endSession, CreateSessionInput } from './session';

/** In-memory KeyValueStore mirroring vscode.Memento (globalState). */
class MemStore implements KeyValueStore {
    private map = new Map<string, unknown>();
    get<T>(key: string): T | undefined { return this.map.get(key) as T | undefined; }
    async update(key: string, value: unknown): Promise<void> { this.map.set(key, value); }
}

const base: CreateSessionInput = {
    provider_id: 'augment-cli',
    provider_name: 'Augment CLI',
    repo_path: '/work/app',
    original_user_request: 'Add a health endpoint',
    generated_prompt: 'PROMPT',
};

describe('toSummary', () => {
    it('never includes the raw output buffer (no secret leakage)', () => {
        const s = createSession(base);
        appendOutput(s, 'export OPENAI_API_KEY=sk-SECRET-LEAK-123');
        const summary = toSummary(s) as Record<string, unknown>;
        expect('output_buffer' in summary).toBe(false);
        expect(JSON.stringify(summary)).not.toContain('SECRET-LEAK');
    });
});

describe('SessionHistory', () => {
    let store: MemStore;
    let history: SessionHistory;
    beforeEach(() => { store = new MemStore(); history = new SessionHistory(store); });

    it('starts empty', () => {
        expect(history.list()).toEqual([]);
    });

    it('saves and lists newest-first', async () => {
        const a = createSession(base);
        const b = createSession(base);
        await history.save(a);
        await history.save(b);
        const list = history.list();
        expect(list.length).toBe(2);
        expect(list[0].session_id).toBe(b.session_id);
    });

    it('does not persist secrets from the session output', async () => {
        const s = createSession(base);
        appendOutput(s, 'token=ghp_TOPSECRETTOKEN');
        await history.save(s);
        expect(JSON.stringify(store.get('agentNeo.terminalAgent.history')))
            .not.toContain('TOPSECRET');
    });

    it('upserts the same session id in place', async () => {
        const s = createSession(base);
        await history.save(s);
        endSession(s, 'completed');
        s.final_summary = 'all good';
        await history.save(s);
        const list = history.list();
        expect(list.length).toBe(1);
        expect(list[0].status).toBe('completed');
        expect(list[0].final_summary).toBe('all good');
    });

    it('bounds history to maxEntries (newest kept)', async () => {
        const h = new SessionHistory(store, 3);
        const ids: string[] = [];
        for (let i = 0; i < 5; i++) {
            const s = createSession(base);
            ids.push(s.session_id);
            await h.save(s);
        }
        const list = h.list();
        expect(list.length).toBe(3);
        expect(list[0].session_id).toBe(ids[4]);
        expect(list.some(x => x.session_id === ids[0])).toBe(false);
    });

    it('gets by id and clears', async () => {
        const s = createSession(base);
        await history.save(s);
        expect(history.get(s.session_id)?.session_id).toBe(s.session_id);
        await history.clear();
        expect(history.list()).toEqual([]);
    });
});
