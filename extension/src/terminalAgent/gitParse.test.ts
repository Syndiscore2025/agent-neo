import { describe, it, expect } from 'vitest';
import { parseRecentCommits, summarizeGitStatus } from './gitParse';

describe('parseRecentCommits', () => {
    it('trims, drops blanks, and bounds to the limit', () => {
        const log = 'abc fix bug\n\n  def add test  \nghi refactor\n';
        expect(parseRecentCommits(log, 2)).toEqual(['abc fix bug', 'def add test']);
    });

    it('returns [] for empty input', () => {
        expect(parseRecentCommits('')).toEqual([]);
    });
});

describe('summarizeGitStatus', () => {
    it('classifies staged / unstaged / untracked', () => {
        const porcelain = [
            'M  staged.ts',
            ' M unstaged.ts',
            'MM both.ts',
            '?? new.ts',
        ].join('\n');
        const s = summarizeGitStatus(porcelain);
        expect(s.stagedFiles.sort()).toEqual(['both.ts', 'staged.ts']);
        expect(s.unstagedFiles.sort()).toEqual(['both.ts', 'unstaged.ts']);
        expect(s.untracked).toEqual(['new.ts']);
        expect(s.changedFiles.sort()).toEqual(
            ['both.ts', 'new.ts', 'staged.ts', 'unstaged.ts'],
        );
    });

    it('resolves renames to the new path', () => {
        const s = summarizeGitStatus('R  old.ts -> new.ts');
        expect(s.stagedFiles).toEqual(['new.ts']);
        expect(s.changedFiles).toEqual(['new.ts']);
    });

    it('handles empty status as no changes', () => {
        const s = summarizeGitStatus('');
        expect(s.changedFiles).toEqual([]);
    });
});
