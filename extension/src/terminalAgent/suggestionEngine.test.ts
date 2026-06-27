import { describe, it, expect } from 'vitest';
import { buildSuggestions, SuggestionInput } from './suggestionEngine';
import { ParsedRun } from './outputParser';
import { ClaimVerification } from './repoWatcher';

function parsed(over: Partial<ParsedRun> = {}): ParsedRun {
    return {
        milestones: [], errors: [], warnings: [], completed: true,
        tests: { detected: false, passed: 0, failed: 0 },
        claimedFiles: [], claimedCommit: false, commitHashes: [],
        ...over,
    };
}
function verification(over: Partial<ClaimVerification> = {}): ClaimVerification {
    return {
        claimedFiles: [], actuallyChanged: [], verified: [],
        unverifiedClaims: [], unclaimedChanges: [], claimedCommit: false,
        commitsCreated: [], commitClaimConsistent: true, ...over,
    };
}
function input(over: Partial<SuggestionInput> = {}): SuggestionInput {
    return {
        status: 'completed', parsed: parsed(), verification: verification(),
        changedFiles: [], branchChanged: false, commitsCreated: [],
        safetyFlags: [], userRequest: 'do a thing', ...over,
    };
}

describe('buildSuggestions', () => {
    it('suggests fixing errors and failing tests with prompts', () => {
        const s = buildSuggestions(input({
            parsed: parsed({ errors: [{ message: 'e', raw: 'e' }], tests: { detected: true, passed: 1, failed: 2 } }),
        }));
        const ids = s.map(x => x.id);
        expect(ids).toContain('fix-errors');
        expect(ids).toContain('fix-tests');
        expect(s.find(x => x.id === 'fix-tests')?.prompt).toContain('2');
    });

    it('flags unverified claims and unclaimed changes', () => {
        const s = buildSuggestions(input({
            verification: verification({ unverifiedClaims: ['a.ts'], unclaimedChanges: ['b.ts'] }),
        }));
        const ids = s.map(x => x.id);
        expect(ids).toContain('unverified');
        expect(ids).toContain('unclaimed');
    });

    it('recommends adding tests and reviewing the diff when changes are uncommitted', () => {
        const s = buildSuggestions(input({ changedFiles: ['a.ts', 'b.ts'] }));
        const ids = s.map(x => x.id);
        expect(ids).toContain('add-tests');
        expect(ids).toContain('review-diff');
    });

    it('leads with a danger safety suggestion', () => {
        const s = buildSuggestions(input({
            safetyFlags: [{ rule: 'rm-rf', detail: 'd', severity: 'danger' }],
        }));
        expect(s[0].id).toBe('safety');
    });

    it('caps at 8 suggestions', () => {
        const s = buildSuggestions(input({
            parsed: parsed({ errors: [{ message: 'e', raw: 'e' }], tests: { detected: true, passed: 0, failed: 1 } }),
            verification: verification({ unverifiedClaims: ['a'], unclaimedChanges: ['b'] }),
            changedFiles: ['a', 'b'], branchChanged: true, commitsCreated: ['c1'],
            safetyFlags: [{ rule: 'r', detail: 'd', severity: 'danger' }],
        }));
        expect(s.length).toBeLessThanOrEqual(8);
    });

    it('falls back to a generic next-step when nothing notable happened', () => {
        const s = buildSuggestions(input());
        expect(s.some(x => x.id === 'next-step' || x.id === 'run-suite')).toBe(true);
    });
});
