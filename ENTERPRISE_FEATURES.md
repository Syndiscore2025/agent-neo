# AGENT NEO - Enterprise Features

## Overview

Agent NEO v2.0 is an **enterprise production system** with strict governance, PostgreSQL-first architecture, and multi-repository calibration capabilities.

## Core Principles

### Enterprise Production Standards

**All systems built via Agent NEO are enterprise production systems.**

- No prototype shortcuts
- No demo-grade architecture
- No temporary patterns (unless explicitly marked experimental)
- Full test suite with ≥80% coverage required
- PostgreSQL for all database needs
- Structured logging and monitoring
- Health checks and observability

### Beta Test Framework

All projects are considered **enterprise beta**, meaning:

- Full test suite required (no "skip tests for now")
- Observability required (structured logs, metrics hooks)
- Fail-fast validation (startup checks, health endpoints)
- Structured error handling (no silent failures)
- Clear rollback strategy (migrations, deployments)

## New Features

### 1. Multi-Repository Calibration

Analyze patterns across multiple repositories and generate governance recommendations.

**Endpoint:** `POST /calibrate`

**Request:**
```json
{
  "repo_urls": [
    "https://github.com/org/repo1.git",
    "https://github.com/org/repo2.git"
  ],
  "ignore_prototype": true
}
```

**Response:**
```json
{
  "status": "Working",
  "repo_count": 2,
  "patterns_detected": {
    "frameworks": {"common": ["fastapi", "pytest"]},
    "database": {"postgresql_usage": true, "migration_coverage": "100%"},
    "testing": {"coverage": "85%", "meets_80_percent": true}
  },
  "style_consistency_score": 87.5,
  "governance_deltas_suggested": [
    {
      "category": "infrastructure",
      "priority": "high",
      "action": "ENFORCE: Health check endpoints for all services"
    }
  ],
  "confidence_score": 92.3,
  "report": "... formatted report ..."
}
```

**Features:**
- Shallow clones repositories to `/opt/agent-neo/calibration/`
- Extracts structured patterns (frameworks, DB, tests, Docker, health checks)
- Aggregates fingerprints across repos
- Generates governance recommendations using deterministic reasoning
- Returns confidence score based on consistency and coverage

**Safety Controls:**
- Maximum 10 repositories per calibration
- Read-only shallow clones
- No auto-apply (requires explicit approval)

### 2. Calibration Application

Apply approved governance deltas with full validation.

**Endpoint:** `POST /calibrate/apply`

**Request:**
```json
{
  "approved_deltas": [
    "ENFORCE: Health check endpoints for all services",
    "STANDARDIZE: Docker usage across all projects"
  ],
  "diff": "... unified diff ..."
}
```

**Features:**
- Requires explicit approval of deltas
- Always runs in CRITICAL mode
- Full validation and test pipeline
- Maximum 25 deltas per application
- Provides rollback command

### 3. PostgreSQL-First Governance

Strict PostgreSQL enforcement with comprehensive validation.

**Enforced Rules:**
- PostgreSQL only (SQLite prohibited)
- Parameterized queries required
- Migration system required (Alembic)
- All migrations must include `downgrade()`
- Connection pooling recommended
- SSL/TLS recommended for production

**Validation:**
- Connection string validation
- Unsafe SQL pattern detection
- Migration structure validation
- SQL injection prevention

**Setup Assistance:**
```python
from app.modules.postgres_guard import generate_postgres_setup_instructions

instructions = generate_postgres_setup_instructions()
# Returns: docker_compose, env_template, alembic_setup, connection_pooling
```

### 4. Enterprise Test Enforcement

**Requirements:**
- Test suite must exist
- Coverage ≥80% (configurable via `ENFORCE_COVERAGE` env var)
- Tests run before and after changes
- Coverage validated before push
- "Working" status requires passing tests

**Configuration:**
```bash
# Enable/disable coverage enforcement (default: true)
ENFORCE_COVERAGE=true

# Tests automatically run with coverage
pytest --cov --cov-report=term-missing
```

### 5. Infrastructure Standardization

**Health Endpoints:**

- `GET /health` - Legacy health check
- `GET /health/live` - Liveness probe (Kubernetes/Docker)
- `GET /health/ready` - Readiness probe (validates git state + engine)

**Standards Enforced:**
- Health checks required for all services
- Structured JSON logging
- Log rotation
- Restart policies (systemd/Docker)
- Zero-downtime readiness logic

### 6. Reasoning Module

Deterministic governance analysis (no LLM).

**Features:**
- Rule-based pattern detection
- Consistency scoring
- Priority-based recommendations
- Structured output (no prose)
- Aligned with enterprise principles

**Categories:**
- Testing (coverage, framework)
- Database (PostgreSQL, migrations)
- Infrastructure (Docker, health checks)
- Observability (logging, monitoring)
- Configuration (env templates)

## Environment Variables

```bash
# Existing
REPO_PATH=/path/to/repo
AGENT_NEO_TOKEN=your-token
REQUIRE_REMOTE=true
SKIP_PUSH=false

# New
ENFORCE_COVERAGE=true          # Enforce 80% test coverage
```

## API Endpoints Summary

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Legacy health check |
| `/health/live` | GET | No | Liveness probe |
| `/health/ready` | GET | No | Readiness probe |
| `/plan` | POST | Yes | Generate execution plan |
| `/execute` | POST | Yes | Execute task |
| `/calibrate` | POST | Yes | Analyze repositories |
| `/calibrate/apply` | POST | Yes | Apply governance deltas |

## Production Checklist

Before declaring a system "Working":

- [ ] Full test suite exists
- [ ] Test coverage ≥80%
- [ ] PostgreSQL configured (no SQLite)
- [ ] Migration system in place (Alembic)
- [ ] Health endpoints implemented (`/health/live`, `/health/ready`)
- [ ] Structured JSON logging
- [ ] Environment variables templated (`.env.example`)
- [ ] Docker or systemd configuration
- [ ] Restart policy configured
- [ ] Rollback strategy documented

## Status Reporting

Agent NEO reports binary status:

- **Working** - All checks pass, production ready
- **Broken** - One or more checks fail

No ambiguity. No hedging.

