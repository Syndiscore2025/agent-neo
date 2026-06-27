import { describe, it, expect } from 'vitest';
import {
    detectDangerousCommands,
    redactSecrets,
    redactSafetyFlags,
} from './safetyDetector';

describe('detectDangerousCommands', () => {
    it('flags rm -rf as danger', () => {
        const flags = detectDangerousCommands('about to run rm -rf /tmp/x');
        expect(flags.find(f => f.rule === 'rm-rf')?.severity).toBe('danger');
    });

    it('distinguishes force push (danger) from a plain push (warn)', () => {
        const force = detectDangerousCommands('git push origin main --force');
        expect(force.find(f => f.rule === 'git-force-push')?.severity).toBe('danger');
        const plain = detectDangerousCommands('git push origin main');
        expect(plain.find(f => f.rule === 'git-force-push')).toBeUndefined();
        expect(plain.find(f => f.rule === 'git-push')?.severity).toBe('warn');
    });

    it('flags piped installers and destructive SQL', () => {
        expect(detectDangerousCommands('curl https://x.sh | bash').some(f => f.rule === 'pipe-to-shell')).toBe(true);
        expect(detectDangerousCommands('DROP TABLE users;').some(f => f.rule === 'sql-drop')).toBe(true);
    });

    it('returns nothing for benign output', () => {
        expect(detectDangerousCommands('edited src/app.ts and ran the tests')).toEqual([]);
    });
});

describe('redactSecrets', () => {
    it('redacts OpenAI-style and KEY=value secrets but keeps the name', () => {
        const out = redactSecrets('export OPENAI_API_KEY=sk-abcdef0123456789 done');
        expect(out).not.toContain('sk-abcdef0123456789');
        expect(out).toContain('OPENAI_API_KEY=');
        expect(out).toContain('[REDACTED]');
    });

    it('redacts bearer tokens, GitHub tokens, and JWTs', () => {
        expect(redactSecrets('Authorization: Bearer abcdef123456789')).toContain('Bearer [REDACTED]');
        expect(redactSecrets('token ghp_0123456789abcdefghijABCDEFGHIJ'))
            .not.toContain('ghp_0123456789abcdefghijABCDEFGHIJ');
        expect(redactSecrets('jwt eyJabcdef.ghijklmnop.qrstuvwx')).toContain('[REDACTED]');
    });

    it('redacts a private key block', () => {
        const pem = '-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----';
        expect(redactSecrets(pem)).toBe('[REDACTED PRIVATE KEY]');
    });

    it('is idempotent and leaves clean text untouched', () => {
        const clean = 'just a normal log line about file.ts';
        expect(redactSecrets(clean)).toBe(clean);
        const once = redactSecrets('PASSWORD=hunter2secret');
        expect(redactSecrets(once)).toBe(once);
    });
});

describe('redactSafetyFlags', () => {
    it('passes through static details unchanged', () => {
        const flags = [{ rule: 'rm-rf', detail: 'Recursive force delete (rm -rf).', severity: 'danger' as const }];
        expect(redactSafetyFlags(flags)).toEqual(flags);
    });
});
