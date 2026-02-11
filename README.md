# AGENT NEO

Production-grade remote execution agent for safe, automated code deployment.

## Overview

AGENT NEO is a remote execution agent that:
- Integrates with Augment as a Remote Agent
- Auto-generates and applies diffs safely
- Auto-commits and auto-pushes to main (RAPID mode)
- Enforces strict kernel safety rules
- Provides rollback commands for every change

## Modes

### RAPID Mode
- **Trigger**: Tasks without critical keywords
- **Behavior**: Auto-commit + auto-push to main
- **Use case**: Fast iteration on non-critical code

### CRITICAL Mode
- **Trigger**: Tasks containing critical keywords (auth, security, schema, migration, etc.)
- **Behavior**: Auto-commit, but push requires explicit force flag
- **Use case**: Changes requiring human review

## Architecture

```
agent-neo/
├── app/
│   ├── main.py              # FastAPI application
│   ├── core/                # Core enforcement logic
│   │   ├── engine.py        # Main execution pipeline
│   │   ├── modes.py         # Mode detection
│   │   ├── policy.py        # Push policy enforcement
│   │   ├── validation.py    # Diff validation
│   │   ├── contracts.py     # Pydantic models
│   │   └── output.py        # Structured output
│   ├── modules/             # Functional modules
│   │   ├── git_guard.py     # Git safety checks
│   │   ├── patch_git.py     # Patch application
│   │   ├── tests_runner.py  # Test execution
│   │   ├── repo_context.py  # Repository scanning
│   │   └── diff_generator.py # Diff generation
│   └── kernel/              # Non-negotiable rules
│       ├── KERNEL.md
│       ├── STYLE.md
│       ├── GUARDRAILS.md
│       └── PLAYBOOKS.md
├── deploy/                  # Deployment configs
├── scripts/                 # Deployment scripts
└── tests/                   # Test suite
```

## Installation

### Local Development

```bash
# Clone repository
git clone <repo-url>
cd agent-neo

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set REPO_PATH

# Run tests
pytest

# Start server
python -m app.main
```

### Production Deployment (DigitalOcean)

```bash
# On your DigitalOcean droplet
sudo bash scripts/bootstrap.sh

# The script will:
# - Install dependencies
# - Create service user
# - Setup systemd service
# - Configure nginx
# - Setup HTTPS (if domain provided)
```

## API Endpoints

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "Working",
  "branch": "main",
  "clean": true,
  "remote": "reachable"
}
```

### POST /plan
Generate execution plan.

**Request:**
```json
{
  "task_id": "task-123",
  "description": "Add new feature",
  "diff": "...",
  "force": false
}
```

**Response:**
```json
{
  "task_id": "task-123",
  "mode": "RAPID",
  "files_to_modify": ["app/main.py"],
  "estimated_lines": 50,
  "validation_warnings": [],
  "critical_keywords_found": []
}
```

### POST /execute
Execute task with diff.

**Request:**
```json
{
  "task_id": "task-123",
  "description": "Add new feature",
  "diff": "--- a/file.py\n+++ b/file.py\n...",
  "force": false
}
```

**Response:**
```json
{
  "status": "Working",
  "task_id": "task-123",
  "mode": "RAPID",
  "commit_sha": "abc123",
  "summary": "Successfully applied changes...",
  "files_changed": ["app/main.py"],
  "lines_changed": 50,
  "pushed": true,
  "verify_steps": ["git show abc123", "git log -1 abc123"],
  "rollback_command": "git revert abc123 --no-edit && git push origin main"
}
```

## Safety Rules

### Validation Rules
- Max 20 files changed per operation
- Max 2000 lines changed in RAPID mode
- Max 40% deletion per file
- No forbidden patterns (git reset, DROP TABLE, etc.)
- No Dockerfile changes in RAPID mode
- No schema migrations in RAPID mode

### Git Safety
- Must be on main branch
- Working tree must be clean
- No detached HEAD
- Remote must be reachable
- Never force push
- Never rebase
- Always provide rollback command

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test
pytest tests/test_engine.py
```

Minimum 80% coverage required.

## Monitoring

```bash
# Service status
systemctl status agent-neo

# Service logs
journalctl -u agent-neo -f

# Nginx logs
tail -f /var/log/nginx/agent-neo.access.log
tail -f /var/log/nginx/agent-neo.error.log
```

## Rollback

Every successful commit includes a rollback command:

```bash
git revert <commit_sha> --no-edit && git push origin main
```

## Status

Binary status reporting:
- **Working**: All systems operational
- **Broken**: Something failed

No ambiguity.

## License

Production-ready infrastructure. No placeholder code.

