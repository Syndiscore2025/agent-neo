# Agent NEO - Postman Collection Guide

## 🚀 Quick Start

### 1. Import the Collection

1. Open Postman
2. Click **Import** button
3. Select `postman_collection.json`
4. Collection will appear in your workspace

### 2. Configure Environment Variables

The collection uses two variables that you need to set:

| Variable | Value | Description |
|----------|-------|-------------|
| `BASE_URL` | `https://agent-neo-app-yrmdg.ondigitalocean.app` | Your deployed app URL |
| `BEARER_TOKEN` | `your-secret-token-here` | Your authentication token |

**To set variables:**
1. Click on the collection name
2. Go to **Variables** tab
3. Update `BEARER_TOKEN` with your actual token
4. Save

### 3. Test the API

Start with the health checks (no auth required):
- ✅ Root
- ✅ Health Check (Legacy)
- ✅ Liveness Probe
- ✅ Readiness Probe

Then test authenticated endpoints:
- 🔐 Plan Task
- 🔐 Execute Task
- 🔐 Calibration endpoints

---

## 📋 API Endpoints Overview

### Health Checks (No Auth Required)

#### `GET /`
Root endpoint - returns agent info and version

#### `GET /health`
Legacy health check - returns git state and status

#### `GET /health/live`
Liveness probe - checks if app is running

#### `GET /health/ready`
Readiness probe - checks if app is ready to serve traffic

---

### Task Execution (Auth Required)

#### `POST /plan`
Generate execution plan for a task

**Request Body:**
```json
{
  "task_id": "task-001",
  "description": "Add a new utility function",
  "mode": "RAPID"  // or "CRITICAL"
}
```

**Response:**
```json
{
  "task_id": "task-001",
  "mode": "RAPID",
  "files_to_modify": ["app/utils.py"],
  "estimated_lines": 15,
  "validation_warnings": [],
  "critical_keywords_found": []
}
```

#### `POST /execute`
Execute a task with optional diff

**Request Body:**
```json
{
  "task_id": "task-002",
  "description": "Add logging to startup",
  "mode": "RAPID",
  "diff": "optional unified diff",
  "force": false
}
```

**Response:**
```json
{
  "status": "Working",
  "task_id": "task-002",
  "mode": "RAPID",
  "commit_sha": "abc123...",
  "summary": "Successfully applied changes",
  "files_changed": ["app/main.py"],
  "lines_changed": 5,
  "pushed": false
}
```

---

### Calibration (Auth Required)

#### `GET /calibrate/status`
Get current calibration status and cache info

#### `POST /calibrate/discover`
Discover repositories from configured GitHub account

#### `POST /calibrate`
Calibrate Agent NEO from multiple repositories

**Request Body:**
```json
{
  "repo_urls": [
    "https://github.com/example/repo1.git",
    "https://github.com/example/repo2.git"
  ],
  "ignore_prototype": true
}
```

#### `POST /calibrate/apply`
Apply approved calibration deltas

**Request Body:**
```json
{
  "approved_deltas": [
    "Add consistent error handling pattern"
  ],
  "diff": "--- a/governance.yaml\n+++ b/governance.yaml\n..."
}
```

---

## 🔐 Authentication

All endpoints except health checks require Bearer token authentication.

**Header:**
```
Authorization: Bearer your-secret-token-here
```

The collection is pre-configured to use the `{{BEARER_TOKEN}}` variable.

---

## 🎯 Testing Workflow

### 1. Verify Deployment
```
GET /health/ready
```
Should return `200 OK` with `"status": "ready"`

### 2. Plan a Task
```
POST /plan
{
  "task_id": "test-001",
  "description": "Add a comment to main.py",
  "mode": "RAPID"
}
```

### 3. Execute the Task
```
POST /execute
{
  "task_id": "test-001",
  "description": "Add a comment to main.py",
  "mode": "RAPID"
}
```

### 4. Check Calibration Status
```
GET /calibrate/status
```

---

## 📝 Notes

- **RAPID Mode**: Fast execution, no force push
- **CRITICAL Mode**: Includes force push option, stricter validation
- All timestamps are in UTC ISO format
- Diffs must be in unified diff format
- Maximum 10 repositories per calibration request

---

## 🐛 Troubleshooting

### 401 Unauthorized
- Check your `BEARER_TOKEN` is set correctly
- Verify token matches server configuration

### 503 Service Unavailable
- App might be starting up
- Check `/health/live` to verify app is running

### 500 Internal Server Error
- Check request body format
- Verify all required fields are present
- Check server logs in DigitalOcean dashboard

---

## 🔗 Resources

- **Live API**: https://agent-neo-app-yrmdg.ondigitalocean.app
- **GitHub**: https://github.com/Syndiscore2025/agent-neo
- **Docs**: `/docs` (FastAPI auto-generated)

