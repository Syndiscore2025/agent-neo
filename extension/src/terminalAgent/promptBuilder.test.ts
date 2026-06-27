import { describe, it, expect } from 'vitest';
import { buildPrompt, DEFAULT_PROMPT_TEMPLATE } from './promptBuilder';

describe('promptBuilder', () => {
    it('fills present variables correctly', () => {
        const out = buildPrompt('Repo: {{repo_path}}\nTask:\n{{user_request}}', {
            repo_path: '/work/app',
            user_request: 'Add a health endpoint',
        });
        expect(out).toContain('Repo: /work/app');
        expect(out).toContain('Add a health endpoint');
    });

    it('omits missing variables cleanly (no null/undefined/placeholder)', () => {
        const out = buildPrompt(DEFAULT_PROMPT_TEMPLATE, {
            user_request: 'Fix the bug',
        });
        expect(out).not.toContain('{{');
        expect(out).not.toContain('}}');
        expect(out).not.toContain('null');
        expect(out).not.toContain('undefined');
    });

    it('drops label-only blocks when their variable is missing', () => {
        const out = buildPrompt(DEFAULT_PROMPT_TEMPLATE, {
            user_request: 'Fix the bug',
        });
        // No git status was supplied → the whole "Git status:" block is dropped.
        expect(out).not.toContain('Git status:');
        expect(out).not.toContain('Open files:');
        // The task block (its variable present) survives.
        expect(out).toContain('Task:');
        expect(out).toContain('Fix the bug');
    });

    it('preserves the user request verbatim', () => {
        const req = 'Do X; do not do Y. Keep "quotes" and symbols & < > intact.';
        const out = buildPrompt(DEFAULT_PROMPT_TEMPLATE, { user_request: req });
        expect(out).toContain(req);
    });

    it('renders array values as a newline list', () => {
        const out = buildPrompt('Changed files:\n{{changed_files}}', {
            changed_files: ['a.ts', 'b.ts'],
        });
        expect(out).toContain('a.ts');
        expect(out).toContain('b.ts');
    });

    it('treats empty-array / empty-string variables as missing', () => {
        const out = buildPrompt(DEFAULT_PROMPT_TEMPLATE, {
            user_request: 'task',
            changed_files: [],
            git_status: '   ',
        });
        expect(out).not.toContain('Changed files:');
        expect(out).not.toContain('Git status:');
    });

    it('default template always retains the instructions block', () => {
        const out = buildPrompt(DEFAULT_PROMPT_TEMPLATE, { user_request: 'task' });
        expect(out).toContain('Instructions:');
        expect(out).toContain('Do not force-push');
    });
});
