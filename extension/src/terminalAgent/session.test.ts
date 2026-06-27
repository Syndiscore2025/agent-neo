import { describe, it, expect } from 'vitest';
import {
    createSession,
    appendOutput,
    endSession,
    isTerminal,
    CreateSessionInput,
} from './session';

const base: CreateSessionInput = {
    provider_id: 'augment-cli',
    provider_name: 'Augment CLI',
    repo_path: '/work/app',
    original_user_request: 'Add a health endpoint',
    generated_prompt: 'PROMPT BODY',
};

describe('createSession', () => {
    it('fully defaults a session from minimal input', () => {
        const s = createSession(base);
        expect(s.session_id).toBeTruthy();
        expect(s.status).toBe('prompt_review');
        expect(s.edited_prompt).toBe('PROMPT BODY');
        expect(s.current_branch_current).toBe(s.current_branch_at_start);
        expect(s.output_buffer).toBe('');
        expect(s.changed_files).toEqual([]);
        expect(s.tests_detected).toBe(false);
        expect(s.ended_at).toBeNull();
        expect(new Date(s.started_at).toString()).not.toBe('Invalid Date');
    });

    it('honours an explicit edited_prompt and start branch/status', () => {
        const s = createSession({
            ...base,
            edited_prompt: 'EDITED',
            current_branch_at_start: 'main',
            status: 'running',
        });
        expect(s.edited_prompt).toBe('EDITED');
        expect(s.current_branch_at_start).toBe('main');
        expect(s.current_branch_current).toBe('main');
        expect(s.status).toBe('running');
    });

    it('gives distinct session ids', () => {
        expect(createSession(base).session_id).not.toBe(createSession(base).session_id);
    });
});

describe('appendOutput', () => {
    it('appends to the rolling buffer', () => {
        const s = createSession(base);
        appendOutput(s, 'a');
        appendOutput(s, 'b');
        expect(s.output_buffer).toBe('ab');
    });

    it('bounds the buffer to the most recent maxChars', () => {
        const s = createSession(base);
        appendOutput(s, 'x'.repeat(10), 5);
        appendOutput(s, 'YZ', 5);
        expect(s.output_buffer.length).toBe(5);
        expect(s.output_buffer.endsWith('YZ')).toBe(true);
    });
});

describe('endSession / isTerminal', () => {
    it('marks a terminal status with an end timestamp', () => {
        const s = createSession(base);
        expect(isTerminal(s)).toBe(false);
        endSession(s, 'completed');
        expect(s.status).toBe('completed');
        expect(s.ended_at).not.toBeNull();
        expect(isTerminal(s)).toBe(true);
    });

    it('treats running/observing as non-terminal', () => {
        const s = createSession({ ...base, status: 'running' });
        expect(isTerminal(s)).toBe(false);
    });
});
