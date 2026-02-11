# AGENT NEO GUARDRAILS

## DIFF VALIDATION GUARDRAILS

### Size Limits
```python
MAX_FILES_CHANGED = 20
MAX_LINES_CHANGED_RAPID = 2000
MAX_LINES_CHANGED_CRITICAL = 5000
MAX_FILE_DELETION_PERCENT = 40
```

### Format Requirements
- Must be valid unified diff format
- Must include file headers (--- a/file, +++ b/file)
- Must include hunk headers (@@ -x,y +a,b @@)
- Must have context lines

### Forbidden Patterns
```python
FORBIDDEN_PATTERNS = [
    r'git\s+reset',
    r'git\s+rebase',
    r'DROP\s+TABLE',
    r'--force',
    r'FORCE',
]

FORBIDDEN_IN_RAPID = [
    r'ALTER\s+TABLE',
    r'CREATE\s+TABLE',
    r'DROP\s+INDEX',
    r'CREATE\s+INDEX',
]
```

### File Type Restrictions

**RAPID Mode Cannot Modify:**
- Dockerfile
- docker-compose.yml
- *.sql (migration files)
- .github/workflows/* (CI/CD)
- kubernetes/*.yaml
- terraform/*.tf

**CRITICAL Mode Requires Review:**
- All of the above
- requirements.txt
- package.json
- Cargo.toml
- go.mod

## GIT OPERATION GUARDRAILS

### Pre-Operation Checks
```python
def validate_git_state():
    # Must be on main branch
    assert current_branch() == "main"
    
    # Must not be detached HEAD
    assert not is_detached_head()
    
    # Working tree must be clean
    assert is_working_tree_clean()
    
    # Remote must be reachable
    assert can_reach_remote()
```

### Forbidden Git Commands
- `git push --force`
- `git push -f`
- `git reset --hard`
- `git rebase`
- `git commit --amend`
- `git filter-branch`
- `git reflog expire`

### Required Git Commands
- `git apply` (for patches)
- `git add -A` (stage changes)
- `git commit -m` (commit with message)
- `git push origin main` (push to main)

## MODE-SPECIFIC GUARDRAILS

### RAPID Mode
**Allowed:**
- Auto-commit
- Auto-push to main
- Small, focused changes
- Non-critical files

**Blocked:**
- Schema changes
- Infrastructure changes
- Large refactors (>2000 lines)
- Multi-file deletions

### CRITICAL Mode
**Allowed:**
- All changes (with validation)
- Schema migrations
- Infrastructure updates
- Large refactors

**Blocked:**
- Auto-push (unless force=true)
- Unreviewed destructive changes

## TEST GUARDRAILS

### 100% Test Pass Rate Requirement
**MANDATORY: All tests must pass before proceeding to any new task.**

```python
# Non-negotiable rule
REQUIRED_TEST_PASS_RATE = 100  # 100% of tests must pass

def enforce_test_gate():
    """
    Block all task execution until test suite passes 100%.
    This is a hard gate - no exceptions.
    """
    result = run_test_suite()
    if result.passed_count != result.total_count:
        raise TestGateError(
            f"Test gate failed: {result.passed_count}/{result.total_count} tests passed. "
            f"Required: 100%. Fix failing tests before proceeding."
        )
```

### Pre-Apply Tests
- Run existing test suite
- **Must achieve 100% pass rate** before applying diff
- Capture baseline coverage

### Post-Apply Tests
- Run full test suite
- **Must achieve 100% pass rate** before commit
- Coverage must not decrease
- New code must have tests

### Test Requirements
```python
MIN_COVERAGE_PERCENT = 80
MIN_NEW_CODE_COVERAGE_PERCENT = 90
REQUIRED_TEST_PASS_RATE = 100  # Mandatory 100% pass rate
```

## ROLLBACK GUARDRAILS

### Rollback Command Generation
```python
def generate_rollback(commit_sha: str) -> str:
    return f"git revert {commit_sha} --no-edit && git push origin main"
```

**Every successful commit must:**
- Generate rollback command
- Include in response
- Log for audit trail

### Rollback Validation
- Rollback command must be tested
- Must not use `--force`
- Must preserve history

## API GUARDRAILS

### Rate Limiting
```python
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_HOUR = 100
```

### Request Validation
- Reject empty diffs
- Reject non-diff content
- Reject malformed JSON
- Reject missing required fields

### Response Requirements
- Always return structured JSON
- Always include mode
- Always include validation results
- Always include rollback command (if committed)

## LOGGING GUARDRAILS

### Required Log Fields
```python
LOG_FIELDS = [
    "timestamp",
    "task_id",
    "mode",
    "operation",
    "status",
    "commit_sha",
    "files_changed",
    "lines_changed",
]
```

### Forbidden in Logs
- Secrets
- API keys
- Passwords
- Tokens
- Full file contents

## SECURITY GUARDRAILS

### Input Sanitization
- Escape shell commands
- Validate file paths
- Reject path traversal attempts
- Validate git URLs

### Execution Safety
- No `eval()` or `exec()`
- No shell=True without validation
- Timeout on subprocess calls
- Capture and validate output

