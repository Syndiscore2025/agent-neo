import { describe, it, expect } from 'vitest';
import {
    buildRepoState,
    diffRepoState,
    verifyClaims,
    RepoState,
} from './repoWatcher';

describe('buildRepoState', () => {
    it('normalises branch, status, and recent commits', () => {
        const state = buildRepoState(
            'main\n',
            ['M  staged.ts', ' M unstaged.ts', '?? new.ts'].join('\n'),
            'abc first\ndef second\n',
        );
        expect(state.branch).toBe('main');
        expect(state.staged).toEqual(['staged.ts']);
        expect(state.unstaged).toEqual(['unstaged.ts']);
        expect(state.untracked).toEqual(['new.ts']);
        expect(state.changed.sort()).toEqual(['new.ts', 'staged.ts', 'unstaged.ts']);
        expect(state.commits).toEqual(['abc first', 'def second']);
    });

    it('maps empty branch to null', () => {
        expect(buildRepoState('', '', '').branch).toBeNull();
    });
});

const base: RepoState = {
    branch: 'main', staged: [], unstaged: ['a.ts'], untracked: [],
    changed: ['a.ts'], commits: ['c1 old'],
};

describe('diffRepoState', () => {
    it('reports newly changed files, commits, and branch switches', () => {
        const after: RepoState = {
            branch: 'feature', staged: ['b.ts'], unstaged: ['a.ts'], untracked: ['c.ts'],
            changed: ['a.ts', 'b.ts', 'c.ts'], commits: ['c2 new', 'c1 old'],
        };
        const d = diffRepoState(base, after);
        expect(d.branchChanged).toBe(true);
        expect(d.previousBranch).toBe('main');
        expect(d.currentBranch).toBe('feature');
        expect(d.newlyChanged.sort()).toEqual(['b.ts', 'c.ts']);
        expect(d.newlyStaged).toEqual(['b.ts']);
        expect(d.newlyUntracked).toEqual(['c.ts']);
        expect(d.newCommits).toEqual(['c2 new']);
    });

    it('reports no change for identical snapshots', () => {
        const d = diffRepoState(base, base);
        expect(d.branchChanged).toBe(false);
        expect(d.newlyChanged).toEqual([]);
        expect(d.newCommits).toEqual([]);
    });
});

describe('verifyClaims', () => {
    const diff = diffRepoState(base, {
        branch: 'main', staged: [], unstaged: ['a.ts', 'b.ts'], untracked: [],
        changed: ['a.ts', 'b.ts'], commits: ['c1 old'],
    });

    it('splits claims into verified / unverified / unclaimed', () => {
        const v = verifyClaims(['b.ts', 'ghost.ts'], false, diff);
        expect(v.verified).toEqual(['b.ts']);
        expect(v.unverifiedClaims).toEqual(['ghost.ts']);
        expect(v.unclaimedChanges).toEqual([]);
    });

    it('flags real changes the CLI never claimed', () => {
        const v = verifyClaims([], false, diff);
        expect(v.unclaimedChanges).toEqual(['b.ts']);
        expect(v.verified).toEqual([]);
    });

    it('normalises Windows separators before comparing', () => {
        const winDiff = diffRepoState(base, {
            branch: 'main', staged: [], unstaged: ['a.ts', 'src/x.ts'], untracked: [],
            changed: ['a.ts', 'src/x.ts'], commits: ['c1 old'],
        });
        const v = verifyClaims(['src\\x.ts'], false, winDiff);
        expect(v.verified).toEqual(['src/x.ts']);
        expect(v.unverifiedClaims).toEqual([]);
    });

    it('marks a commit claim consistent only when a commit appeared', () => {
        const noCommit = verifyClaims([], true, diff);
        expect(noCommit.commitsCreated).toEqual([]);
        expect(noCommit.commitClaimConsistent).toBe(false);

        const committed = diffRepoState(base, {
            ...base, commits: ['c2 new', 'c1 old'],
        });
        const withCommit = verifyClaims([], true, committed);
        expect(withCommit.commitsCreated).toEqual(['c2 new']);
        expect(withCommit.commitClaimConsistent).toBe(true);
    });
});
