"""
AGENT NEO - FastAPI Application
Production-ready remote execution agent.
"""

import os
import logging
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

from app.core.engine import Engine
from app.core.contracts import (
    TaskRequest,
    ExecuteResponse,
    PlanResponse,
    HealthResponse,
    CalibrationRequest,
    CalibrationResponse,
    CalibrationApplyRequest
)
from app.core.auth import verify_bearer_token
from app.modules.git_guard import get_git_state, GitGuardError

# Interactive layer imports
from app.interactive.contracts import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ApprovalRequest,
    ApprovalResponse,
    CompletionRequest,
    CompletionResponse,
    AttachmentUpload,
    AttachmentResponse,
    SuggestionRequest,
    SuggestionResponse,
    SummarizeRequest,
    SessionSummaryResponse,
    RollbackRequest,
    RollbackResponse,
    AutoRunRequest,
    AutoRunResponse,
)
from app.interactive.orchestrator import get_orchestrator
from app.interactive.session_manager import get_session_manager
from app.interactive.completion_service import get_completion_service
from app.interactive.attachment_handler import get_attachment_handler
from app.interactive.suggestion_engine import get_suggestion_engine


# Configure logging
logging.basicConfig(
    format='[AGENT NEO] [%(asctime)s] [%(levelname)s] [%(module)s] %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# Global engine instance
engine: Engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global engine
    
    # Startup
    logger.info("AGENT NEO starting up...")

    # Load configuration
    # Default to /workspace for cloud deployments (DigitalOcean, Render, etc.)
    # or current directory for local development
    default_repo_path = os.getenv("HOME", "/workspace") if os.path.exists("/workspace") else os.getcwd()
    repo_path = os.getenv("REPO_PATH", default_repo_path)

    logger.info(f"Repository path: {repo_path}")

    # Initialize engine
    try:
        engine = Engine(repo_path)
        logger.info("Engine initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")
        raise

    # Validate git state (skip remote validation in cloud environments)
    try:
        from app.modules.git_guard import validate_git_state
        # Don't require remote in cloud deployments
        is_cloud = os.path.exists("/workspace") or os.getenv("DYNO") or os.getenv("RENDER")
        require_remote = os.getenv("REQUIRE_REMOTE", "false" if is_cloud else "true").lower() == "true"
        validate_git_state(repo_path, require_remote=require_remote)
        logger.info("Git state validated successfully")
    except GitGuardError as e:
        logger.warning(f"Git state validation failed: {e}")
        # Don't fail startup in cloud environments
        if not is_cloud:
            raise
    
    logger.info("AGENT NEO ready")
    
    yield
    
    # Shutdown
    logger.info("AGENT NEO shutting down...")


# Create FastAPI app
app = FastAPI(
    title="AGENT NEO",
    description="Production-grade remote execution agent with interactive coding partner",
    version="2.1.0",
    lifespan=lifespan
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "Broken",
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint (legacy).

    Returns:
        HealthResponse with current git state
    """
    try:
        repo_path = os.getenv("REPO_PATH")
        git_state = get_git_state(repo_path)

        # In cloud deployments, relax git state requirements
        is_cloud = os.path.exists("/workspace") or os.getenv("DYNO") or os.getenv("RENDER")

        if is_cloud:
            # For cloud: just check if engine is initialized
            status = "Working" if engine is not None else "Broken"
        else:
            # For local: strict git state validation
            status = "Working" if (
                git_state.branch == "main" and
                git_state.clean and
                not git_state.detached and
                git_state.remote_reachable
            ) else "Broken"

        return HealthResponse(
            status=status,
            branch=git_state.branch,
            clean=git_state.clean,
            remote="reachable" if git_state.remote_reachable else "unreachable"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="Broken",
            branch="unknown",
            clean=False,
            remote="unreachable"
        )


@app.get("/health/live")
async def liveness_probe():
    """
    Liveness probe - checks if application is running.

    Enterprise standard endpoint for Kubernetes/Docker health checks.

    Returns:
        200 if alive, 503 if not
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/ready")
async def readiness_probe():
    """
    Readiness probe - checks if application is ready to serve traffic.

    Enterprise standard endpoint for Kubernetes/Docker health checks.
    Validates git state and engine initialization.

    Returns:
        200 if ready, 503 if not ready
    """
    try:
        # Check if engine is initialized
        if engine is None:
            raise HTTPException(status_code=503, detail="Engine not initialized")

        # Check git state
        repo_path = os.getenv("REPO_PATH")
        git_state = get_git_state(repo_path)

        # In cloud deployments (detached HEAD), just check if engine is initialized
        is_cloud = os.path.exists("/workspace") or os.getenv("DYNO") or os.getenv("RENDER")

        if is_cloud:
            # For cloud: just check engine is initialized (already checked above)
            ready = True
        else:
            # For local: strict git state validation
            ready = (
                git_state.branch == "main" and
                git_state.clean and
                not git_state.detached
            )

        if not ready:
            raise HTTPException(
                status_code=503,
                detail=f"Not ready: branch={git_state.branch}, clean={git_state.clean}, detached={git_state.detached}"
            )

        return {
            "status": "ready",
            "branch": git_state.branch,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/plan", response_model=PlanResponse)
async def plan_task(request: TaskRequest, token: str = Depends(verify_bearer_token)):
    """
    Generate execution plan for a task.

    Requires Bearer token authentication.

    Args:
        request: Task request
        
    Returns:
        PlanResponse with execution plan
    """
    try:
        logger.info(f"Planning task: {request.task_id}")
        plan = engine.plan(request)
        logger.info(f"Plan generated: mode={plan.mode}, files={len(plan.files_to_modify)}")
        return plan
    except Exception as e:
        logger.error(f"Plan generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/execute", response_model=ExecuteResponse)
async def execute_task(request: TaskRequest, token: str = Depends(verify_bearer_token)):
    """
    Execute a task with diff application.

    Requires Bearer token authentication.

    Args:
        request: Task request with diff

    Returns:
        ExecuteResponse with execution results
    """
    try:
        logger.info(f"Executing task: {request.task_id}")
        
        # Validate diff is provided
        if not request.diff:
            raise HTTPException(
                status_code=400,
                detail="Diff is required for execution"
            )
        
        # Execute task
        response = engine.execute(request)
        
        logger.info(
            f"Task executed: {request.task_id} | "
            f"status={response.status} | "
            f"mode={response.mode} | "
            f"pushed={response.pushed}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calibrate/status")
async def calibrate_status(token: str = Depends(verify_bearer_token)):
    """
    Get current calibration status and cache info.

    Returns status of GitHub discovery configuration and clone cache.
    """
    try:
        from app.modules.github_discovery import get_github_config, validate_github_config
        from app.modules.repo_cloner import get_cache_status

        config = get_github_config()
        validation_errors = validate_github_config(config)
        cache_status = get_cache_status(config.get("cache_dir"))

        return {
            "status": "ready" if not validation_errors else "not_configured",
            "github_configured": not bool(validation_errors),
            "github_owner": config.get("owner"),
            "github_type": config.get("type"),
            "max_repos": config.get("max_repos"),
            "include_topics": list(config.get("include_topics", [])),
            "exclude_topics": list(config.get("exclude_topics", [])),
            "cache_status": cache_status,
            "validation_errors": validation_errors
        }
    except Exception as e:
        logger.error(f"Calibration status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calibrate/discover")
async def calibrate_discover(token: str = Depends(verify_bearer_token)):
    """
    Discover repositories from configured GitHub account.

    Lists filtered repositories ready for calibration.
    Does NOT clone or analyze - only lists.
    """
    try:
        from app.modules.github_discovery import discover_repositories

        result = discover_repositories()

        if result.errors:
            if not result.repos:
                raise HTTPException(status_code=400, detail=result.errors[0])

        return {
            "status": "Working" if result.repos else "Broken",
            "total_found": result.total_found,
            "total_after_filter": result.total_filtered,
            "repos_to_analyze": len(result.repos),
            "filters_applied": result.filters_applied,
            "repos": [r.to_dict() for r in result.repos],
            "errors": result.errors
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Repository discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calibrate", response_model=CalibrationResponse)
async def calibrate_repos(request: CalibrationRequest, token: str = Depends(verify_bearer_token)):
    """
    Calibrate Agent NEO from multiple repositories.

    Analyzes patterns across repositories and generates governance recommendations.
    Does NOT auto-apply changes.

    Requires Bearer token authentication.

    Args:
        request: Calibration request with repo URLs

    Returns:
        CalibrationResponse with analysis and recommendations
    """
    try:
        from pathlib import Path
        import shutil
        from app.modules.repo_miner import clone_repo_shallow, mine_repository
        from app.modules.style_fingerprint import aggregate_fingerprints
        from app.modules.reasoning import analyze_governance_deltas, format_calibration_report

        logger.info(f"Starting calibration with {len(request.repo_urls)} repositories")

        # Create calibration directory (use env var or fallback to /tmp)
        cache_dir_str = os.getenv("CALIBRATION_CACHE_DIR", "/tmp/agent-neo-calibration")
        calibration_dir = Path(cache_dir_str)
        calibration_dir.mkdir(parents=True, exist_ok=True)

        fingerprints = []

        # Clone and mine each repository
        for repo_url in request.repo_urls:
            repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
            repo_path = calibration_dir / repo_name

            # Clean up if exists
            if repo_path.exists():
                shutil.rmtree(repo_path)

            # Clone shallow
            if not clone_repo_shallow(repo_url, repo_path):
                logger.warning(f"Failed to clone {repo_url}, skipping")
                continue

            # Mine repository
            try:
                fingerprint = mine_repository(repo_path, repo_name)
                fingerprints.append(fingerprint)
                logger.info(f"Mined {repo_name}: {fingerprint.total_files} files, {fingerprint.total_lines} lines")
            except Exception as e:
                logger.error(f"Failed to mine {repo_name}: {e}")
                continue

        if not fingerprints:
            return CalibrationResponse(
                status="Broken",
                repo_count=0,
                patterns_detected={},
                style_consistency_score=0.0,
                governance_deltas_suggested=[],
                confidence_score=0.0,
                report="No repositories successfully analyzed"
            )

        # Aggregate fingerprints
        aggregated = aggregate_fingerprints(fingerprints)

        # Analyze with reasoning
        analysis = analyze_governance_deltas(aggregated)

        # Format report
        report = format_calibration_report(analysis)

        logger.info(f"Calibration complete: {len(fingerprints)} repos, confidence {analysis['confidence_score']:.1f}")

        return CalibrationResponse(
            status="Working",
            repo_count=analysis['repo_count'],
            patterns_detected=analysis['patterns_detected'],
            style_consistency_score=analysis['style_consistency_score'],
            governance_deltas_suggested=analysis['governance_deltas_suggested'],
            confidence_score=analysis['confidence_score'],
            report=report
        )

    except Exception as e:
        logger.error(f"Calibration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calibrate/apply", response_model=ExecuteResponse)
async def apply_calibration(request: CalibrationApplyRequest, token: str = Depends(verify_bearer_token)):
    """
    Apply approved calibration deltas.

    Requires explicit approval of deltas and unified diff.
    Runs full validation and test pipeline.

    Requires Bearer token authentication.

    Args:
        request: Calibration apply request with approved deltas and diff

    Returns:
        ExecuteResponse with execution results
    """
    try:
        logger.info(f"Applying calibration with {len(request.approved_deltas)} approved deltas")

        # Validate delta count (safety limit)
        if len(request.approved_deltas) > 25:
            raise HTTPException(
                status_code=400,
                detail="Maximum 25 deltas allowed per calibration apply"
            )

        # Create task request from calibration
        task_request = TaskRequest(
            task_id=f"calibration-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            description=f"Apply calibration deltas: {', '.join(request.approved_deltas[:3])}...",
            diff=request.diff,
            force=False,
            mode="CRITICAL"  # Calibration always uses CRITICAL mode
        )

        # Execute through normal pipeline
        response = engine.execute(task_request)

        logger.info(f"Calibration applied: status={response.status}")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calibration apply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INTERACTIVE ENDPOINTS
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Send a chat message and get response.

    TODO: Implement in SLICE 2
    """
    try:
        orchestrator = get_orchestrator(engine)
        response = await orchestrator.handle_chat(request)
        return response
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    _: str = Depends(verify_bearer_token)
):
    """
    Get chat history for a session.

    TODO: Implement in SLICE 2
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return ChatHistoryResponse(
            session_id=session_id,
            messages=session.messages,
            total_messages=len(session.messages)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chat history failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/approve", response_model=ApprovalResponse)
async def approve_diff(
    request: ApprovalRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Approve or reject a proposed diff.

    TODO: Implement in SLICE 5
    """
    try:
        orchestrator = get_orchestrator(engine)
        response = await orchestrator.handle_approval(request)
        return response
    except Exception as e:
        logger.error(f"Approval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/summarize", response_model=SessionSummaryResponse)
async def summarize_session(
    request: SummarizeRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Summarise the current session and create a new session pre-seeded with
    that summary so the user can continue without losing context.

    Call this when a thread becomes too long to maintain effective context.
    """
    try:
        orchestrator = get_orchestrator(engine)
        response = await orchestrator.handle_summarize(request)
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Session summarise failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/rollback", response_model=RollbackResponse)
async def rollback_last_change(
    request: RollbackRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Undo the last applied diff by running ``git revert --no-edit`` locally.

    The revert commit is created locally only — never pushed automatically.
    """
    try:
        orchestrator = get_orchestrator(engine)
        response = await orchestrator.handle_rollback(request)
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/autorun", response_model=AutoRunResponse)
async def auto_run_task(
    request: AutoRunRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Execute a coding task fully autonomously: plan → diff → apply → verify.

    No intermediate approval prompts — the user triggers it once and the
    orchestrator chains all steps, returning a structured step-by-step result.
    """
    try:
        orchestrator = get_orchestrator(engine)
        response = await orchestrator.handle_auto_run(request)
        return response
    except Exception as e:
        logger.error(f"AutoRun failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chat/session")
async def delete_chat_session(
    session_id: str,
    _: str = Depends(verify_bearer_token)
):
    """
    Delete a chat session.

    TODO: Implement in SLICE 2
    """
    try:
        session_manager = get_session_manager()
        deleted = session_manager.delete_session(session_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/complete", response_model=CompletionResponse)
async def complete(
    request: CompletionRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Generate inline code completion.

    TODO: Implement in SLICE 7
    """
    try:
        completion_service = get_completion_service()
        response = await completion_service.generate_completion(request)
        return response
    except Exception as e:
        logger.error(f"Completion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/attachments/upload", response_model=AttachmentResponse)
async def upload_attachment(
    upload: AttachmentUpload,
    _: str = Depends(verify_bearer_token)
):
    """
    Upload an image or PDF attachment.

    TODO: Implement in SLICE 6
    """
    try:
        attachment_handler = get_attachment_handler()
        response = await attachment_handler.process_attachment(upload)
        return response
    except Exception as e:
        logger.error(f"Attachment upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/attachments/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: str,
    _: str = Depends(verify_bearer_token)
):
    """
    Get attachment by ID.

    TODO: Implement in SLICE 6
    """
    try:
        attachment_handler = get_attachment_handler()
        attachment = attachment_handler.get_attachment(attachment_id)

        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found")

        return attachment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get attachment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/suggestions", response_model=SuggestionResponse)
async def get_suggestions(
    request: SuggestionRequest,
    _: str = Depends(verify_bearer_token)
):
    """
    Get prompt suggestions based on context.

    TODO: Implement in SLICE 8
    """
    try:
        suggestion_engine = get_suggestion_engine()
        response = await suggestion_engine.generate_suggestions(request)
        return response
    except Exception as e:
        logger.error(f"Get suggestions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "agent": "AGENT NEO",
        "version": "2.1.0",
        "status": "Working",
        "endpoints": {
            "health": "/health",
            "health_live": "/health/live",
            "health_ready": "/health/ready",
            "plan": "/plan",
            "execute": "/execute",
            "calibrate_status": "/calibrate/status",
            "calibrate_discover": "/calibrate/discover",
            "calibrate": "/calibrate",
            "calibrate_apply": "/calibrate/apply",
            "chat": "/chat",
            "chat_history": "/chat/history",
            "chat_approve": "/chat/approve",
            "chat_reject": "/chat/reject",
            "chat_summarize": "/chat/summarize",
            "chat_rollback": "/chat/rollback",
            "chat_session": "/chat/session",
            "complete": "/complete",
            "attachments_upload": "/attachments/upload",
            "suggestions": "/suggestions"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

