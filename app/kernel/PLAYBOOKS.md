# AGENT NEO PLAYBOOKS

## PLAYBOOK 1: RAPID MODE EXECUTION

### Trigger
Task does NOT contain critical keywords

### Flow
```
1. Receive task request
2. Detect mode → RAPID
3. Load kernel rules
4. Scan repo context
5. Generate minimal unified diff
6. Validate diff (size, format, patterns)
7. Run pre-apply tests
8. Apply diff via git apply
9. Stage changes (git add -A)
10. Commit with descriptive message
11. AUTO-PUSH to main
12. Run post-apply tests
13. Return response with commit_sha and rollback command
```

### Success Criteria
- All validations pass
- Pre-tests pass
- Diff applies cleanly
- Post-tests pass
- Push succeeds

### Rollback
```bash
git revert <commit_sha> --no-edit && git push origin main
```

## PLAYBOOK 2: CRITICAL MODE EXECUTION

### Trigger
Task contains ANY critical keyword

### Flow
```
1. Receive task request
2. Detect mode → CRITICAL
3. Load kernel rules
4. Scan repo context
5. Generate minimal unified diff
6. Validate diff (relaxed limits)
7. Run pre-apply tests
8. Apply diff via git apply
9. Stage changes (git add -A)
10. Commit with descriptive message
11. BLOCK AUTO-PUSH (unless force=true)
12. Run post-apply tests
13. Return response with summary and verification steps
```

### Success Criteria
- All validations pass
- Pre-tests pass
- Diff applies cleanly
- Post-tests pass
- Summary generated for human review

### Manual Push
Human must review and execute:
```bash
git push origin main
```

## PLAYBOOK 3: VALIDATION FAILURE

### Trigger
Diff fails any validation rule

### Flow
```
1. Detect validation failure
2. Log failure details
3. Rollback any partial changes
4. Return structured error response
5. Include specific validation that failed
6. Include guidance for fixing
```

### Response
```json
{
  "status": "Broken",
  "error": "Validation failed",
  "details": "Diff modifies 25 files (max: 20)",
  "guidance": "Split changes into smaller diffs"
}
```

## PLAYBOOK 4: TEST FAILURE

### Trigger
Pre-apply or post-apply tests fail

### Flow
```
1. Detect test failure
2. Capture test output (last 50 lines)
3. Rollback changes if post-apply
4. Return structured error response
5. Include test output
6. Include files that may need fixing
```

### Response
```json
{
  "status": "Broken",
  "error": "Tests failed",
  "test_output": "...",
  "files_affected": ["app/core/engine.py"]
}
```

## PLAYBOOK 5: GIT OPERATION FAILURE

### Trigger
Git apply, commit, or push fails

### Flow
```
1. Detect git failure
2. Capture git error output
3. Rollback to clean state
4. Return structured error response
5. Include git error details
6. Include recovery steps
```

### Recovery
```bash
# If apply failed
git reset --hard HEAD
git clean -fd

# If push failed (conflict)
git pull --rebase origin main
git push origin main
```

## PLAYBOOK 6: STARTUP

### Trigger
Agent starts

### Flow
```
1. Load environment variables
2. Validate configuration
3. Check repo path exists
4. Validate git repository
5. Check branch is main
6. Check working tree is clean
7. Test remote connectivity
8. Load kernel rules
9. Start FastAPI server
10. Log startup success
```

### Failure Handling
- Missing config → Exit with error
- Invalid repo → Exit with error
- Not on main → Exit with error
- Dirty tree → Exit with error

## PLAYBOOK 7: HEALTH CHECK

### Trigger
GET /health request

### Flow
```
1. Check git repository accessible
2. Check on main branch
3. Check working tree clean
4. Check remote reachable
5. Return health status
```

### Response
```json
{
  "status": "Working",
  "branch": "main",
  "clean": true,
  "remote": "reachable"
}
```

## PLAYBOOK 8: PLAN GENERATION

### Trigger
POST /plan request

### Flow
```
1. Receive task description
2. Detect mode (RAPID/CRITICAL)
3. Scan repo context
4. Identify files to modify
5. Generate execution plan
6. Return plan with mode and affected files
```

### Response
```json
{
  "mode": "RAPID",
  "files_to_modify": ["app/core/engine.py"],
  "estimated_lines": 50,
  "validation_warnings": []
}
```

## PLAYBOOK 9: EMERGENCY STOP

### Trigger
Critical error during execution

### Flow
```
1. Detect critical error
2. Halt all operations
3. Rollback any partial changes
4. Reset to clean state
5. Log incident
6. Return error response
```

### Recovery
```bash
git reset --hard HEAD
git clean -fd
git status
```

## PLAYBOOK 10: AUDIT LOG

### Trigger
Every operation

### Flow
```
1. Log operation start
2. Log validation results
3. Log test results
4. Log git operations
5. Log final status
6. Include all context
```

### Log Entry
```json
{
  "timestamp": "2026-02-11T10:30:00Z",
  "task_id": "task-123",
  "mode": "RAPID",
  "operation": "execute",
  "status": "Working",
  "commit_sha": "abc123",
  "files_changed": 3,
  "lines_changed": 150
}
```

