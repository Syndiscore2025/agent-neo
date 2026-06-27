import { describe, it, expect, beforeEach } from 'vitest';
import {
    detectTestResults,
    extractClaimedFiles,
    detectCommitClaims,
    detectWarnings,
    parseRun,
} from './outputParser';
import { getProviderRegistry, resetProviderRegistry } from './providers/registry';

describe('detectTestResults', () => {
    it('parses jest-style summaries', () => {
        const r = detectTestResults('Tests: 2 failed, 8 passed, 10 total');
        expect(r).toEqual({ detected: true, passed: 8, failed: 2 });
    });

    it('parses pytest-style summaries', () => {
        const r = detectTestResults('===== 5 passed in 0.12s =====');
        expect(r.passed).toBe(5);
        expect(r.failed).toBe(0);
        expect(r.detected).toBe(true);
    });

    it('reports not-detected for output with no test signal', () => {
        expect(detectTestResults('edited a file').detected).toBe(false);
    });
});

describe('extractClaimedFiles', () => {
    it('captures files after action verbs and normalises separators', () => {
        const out = extractClaimedFiles('Created src\\a.ts\nEdited lib/b.js\nupdated README.md');
        expect(out.sort()).toEqual(['README.md', 'lib/b.js', 'src/a.ts']);
    });

    it('ignores URLs and lines without a file', () => {
        expect(extractClaimedFiles('created https://example.com/x.html\nran the build')).toEqual([]);
    });
});

describe('detectCommitClaims', () => {
    it('extracts a git commit hash from bracketed output', () => {
        const r = detectCommitClaims('[main 1a2b3c4] add feature');
        expect(r.commitHashes).toEqual(['1a2b3c4']);
        expect(r.claimedCommit).toBe(true);
    });

    it('treats "nothing to commit" as no commit', () => {
        const r = detectCommitClaims('nothing to commit, working tree clean');
        expect(r.claimedCommit).toBe(false);
        expect(r.commitHashes).toEqual([]);
    });

    it('detects a textual commit claim without a hash', () => {
        expect(detectCommitClaims('I committed the changes').claimedCommit).toBe(true);
    });
});

describe('detectWarnings', () => {
    it('keeps warning lines and drops error lines', () => {
        const w = detectWarnings('WARNING: deprecated API\nError: boom\nwarn: slow');
        expect(w).toEqual(['WARNING: deprecated API', 'warn: slow']);
    });
});

describe('parseRun', () => {
    beforeEach(() => resetProviderRegistry());

    it('combines provider heuristics with generic detectors', () => {
        const provider = getProviderRegistry().get('augment-cli')!;
        const output = [
            'created src/feature.ts',
            'running tests',
            'Tests: 1 failed, 3 passed',
            'Error: something broke',
            '[main abcdef0] wip',
        ].join('\n');
        const r = parseRun(provider, output);
        expect(r.claimedFiles).toContain('src/feature.ts');
        expect(r.tests).toEqual({ detected: true, passed: 3, failed: 1 });
        expect(r.errors.length).toBeGreaterThan(0);
        expect(r.commitHashes).toEqual(['abcdef0']);
        expect(r.claimedCommit).toBe(true);
    });
});
