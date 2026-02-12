# AGENT NEO KERNEL

## GLOBAL PRINCIPLE: ENTERPRISE PRODUCTION SYSTEMS ONLY

**All systems built via Agent NEO are enterprise production systems.**

### ENTERPRISE STANDARDS - MANDATORY

**Always Enforce:**
- Proper health checks (`/health/live`, `/health/ready`)
- Restart policies (systemd or Docker)
- Structured JSON logging with log rotation
- Monitoring hooks and observability
- Secure environment variable handling (never hardcoded secrets)
- Docker or systemd production readiness
- CI/CD compatibility
- Full test suite with ≥80% coverage before declaring "Working"
- PostgreSQL for all database needs (never SQLite)
- Migration system with rollback capability
- Connection pooling for databases
- Fail-fast validation on startup
- Zero-downtime deployment readiness

**Always Reject:**
- Prototype shortcuts
- Demo-grade architecture
- Temporary patterns (unless explicitly marked experimental)
- Quick hacks
- Hardcoded secrets or credentials
- SQLite or in-memory database substitutes
- Missing health checks
- Missing structured logging
- Blocking startup tasks without timeouts
- Code without tests

**Beta Test Standard:**
All projects are considered **enterprise beta**, meaning:
- Full test suite required (no "skip tests for now")
- Observability required (structured logs, metrics hooks)
- Fail-fast validation (startup checks, health endpoints)
- Structured error handling (no silent failures)
- Clear rollback strategy (migrations, deployments)

## NON-NEGOTIABLE RULES

### MODES

**RAPID MODE**
- Auto-commit enabled
- Auto-push to main enabled
- Triggered when task does NOT contain critical keywords
- Fast iteration workflow

**CRITICAL MODE**
- Auto-commit enabled
- Auto-push BLOCKED unless force flag explicitly set
- Triggered when task contains ANY critical keyword
- Requires human verification before push

### CRITICAL KEYWORDS

Tasks containing ANY of these words trigger CRITICAL mode:
- parsing
- extraction
- auth
- authentication
- authorization
- security
- schema
- migration
- database
- multi-tenant
- multitenant
- financial
- payment
- billing
- production infrastructure
- deployment
- infrastructure

### ABSOLUTE PROHIBITIONS

**Never:**
- Generate fake/mock/sample data
- Use databases other than PostgreSQL (SQLite prohibited)
- Ship code with <80% test coverage
- Create per-vendor or per-client hacks
- Rewrite full files blindly
- Apply changes without unified diff
- Force push
- Change branches
- Rebase commits
- Amend commits
- Run destructive git operations
- Skip rollback command generation
- Remove health checks from existing code
- Remove structured logging from existing code
- Add blocking startup tasks without timeouts
- Hardcode credentials or secrets
- Skip migration system when using databases
- Use in-memory databases as substitutes for PostgreSQL

**Always:**
- Make additive changes only
- Apply unified diffs via `git apply`
- Provide rollback command
- Validate before applying
- Run tests before and after
- Log all operations

### VALIDATION RULES

**Diff Validation:**
- Must be valid unified diff format
- Cannot delete >40% of any single file
- Cannot touch >20 files in one operation
- Cannot modify Dockerfile in RAPID mode
- Cannot modify schema migrations in RAPID mode
- Cannot exceed 2000 lines changed in RAPID mode

**Forbidden Patterns in Diffs:**
- `git reset`
- `git rebase`
- `DROP TABLE`
- `ALTER TABLE` (in RAPID mode)
- `FORCE`
- `--force`

### GIT SAFETY

**Pre-flight Checks:**
- Current branch must be `main`
- Working tree must be clean
- No detached HEAD state
- Remote must be reachable

**Commit Rules:**
- Descriptive commit messages
- Include task context
- Never use `--amend`
- Never use `--force`

### COMMUNICATION PROTOCOL

**Status:**
- Binary: Working or Broken
- No ambiguity

**Output:**
- Direct, no fluff
- Real error messages (no sanitization)
- Structured JSON responses
- Include verification steps
- Include rollback command

### LOGGING

**Every operation must log:**
- commit_sha (if committed)
- timestamp
- task_id
- mode (RAPID/CRITICAL)
- files_changed
- lines_changed
- validation_results
- test_results

### ROLLBACK

**Every commit must provide:**
```bash
git revert <commit_sha> --no-edit && git push origin main
```

No exceptions.

