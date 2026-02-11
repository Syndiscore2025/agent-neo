# AGENT NEO STYLE GUIDE

## CODE STYLE

### Python
- PEP 8 compliant
- Type hints required
- Pydantic models for all contracts
- No `Any` types without justification
- Docstrings for public functions
- Max line length: 100 characters

### Structure
- Core: enforcement only, no business logic
- Modules: isolated, single responsibility
- No circular dependencies
- Clear separation of concerns

### Naming
- Functions: `verb_noun` (e.g., `validate_diff`, `apply_patch`)
- Classes: `PascalCase` (e.g., `TaskRequest`, `DiffValidator`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_FILES_CHANGED`)
- Private: prefix with `_`

## ERROR HANDLING

### Exceptions
- Use specific exception types
- Include context in messages
- Never swallow exceptions silently
- Log before raising

### Validation
- Fail fast
- Clear error messages
- Include what was expected vs received
- Provide actionable guidance

## TESTING

### Coverage
- Minimum 80% required
- Test happy path
- Test error cases
- Test edge cases
- Test validation rules

### Test Structure
- Arrange, Act, Assert
- One assertion per test (when possible)
- Descriptive test names
- Use fixtures for setup

## LOGGING

### Levels
- DEBUG: Detailed diagnostic info
- INFO: Confirmation of expected behavior
- WARNING: Something unexpected but handled
- ERROR: Serious problem, operation failed
- CRITICAL: System-level failure

### Format
```
[AGENT NEO] [TIMESTAMP] [LEVEL] [MODULE] MESSAGE
```

### Content
- Include context (task_id, mode, etc.)
- Include relevant data
- No sensitive information
- Structured when possible

## CONFIGURATION

### Environment Variables
- All config via .env
- No hardcoded values
- Validation on startup
- Clear naming (e.g., `REPO_PATH`, `AUTO_PUSH_ENABLED`)

### Defaults
- Safe defaults
- Document all options
- Fail if critical config missing

## DOCUMENTATION

### Code Comments
- Explain WHY, not WHAT
- Document non-obvious behavior
- Keep comments up to date
- Remove dead comments

### API Documentation
- OpenAPI/Swagger for FastAPI
- Request/response examples
- Error response documentation
- Authentication requirements

## SECURITY

### Secrets
- Never log secrets
- Never commit secrets
- Use environment variables
- Rotate regularly

### Input Validation
- Validate all external input
- Sanitize for logging
- Reject malformed requests
- Rate limiting on endpoints

## PERFORMANCE

### Efficiency
- Minimize git operations
- Cache when appropriate
- Async where beneficial
- Clean up resources

### Limits
- Timeout on long operations
- Max diff size
- Max files changed
- Max lines changed

