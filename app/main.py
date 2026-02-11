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
    HealthResponse
)
from app.core.auth import verify_bearer_token
from app.modules.git_guard import get_git_state, GitGuardError


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
    repo_path = os.getenv("REPO_PATH")
    if not repo_path:
        logger.error("REPO_PATH environment variable not set")
        raise RuntimeError("REPO_PATH environment variable required")
    
    logger.info(f"Repository path: {repo_path}")
    
    # Initialize engine
    try:
        engine = Engine(repo_path)
        logger.info("Engine initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")
        raise
    
    # Validate git state
    try:
        from app.modules.git_guard import validate_git_state
        require_remote = os.getenv("REQUIRE_REMOTE", "true").lower() == "true"
        validate_git_state(repo_path, require_remote=require_remote)
        logger.info("Git state validated successfully")
    except GitGuardError as e:
        logger.error(f"Git state validation failed: {e}")
        raise
    
    logger.info("AGENT NEO ready")
    
    yield
    
    # Shutdown
    logger.info("AGENT NEO shutting down...")


# Create FastAPI app
app = FastAPI(
    title="AGENT NEO",
    description="Production-grade remote execution agent",
    version="1.0.0",
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
    Health check endpoint.
    
    Returns:
        HealthResponse with current git state
    """
    try:
        repo_path = os.getenv("REPO_PATH")
        git_state = get_git_state(repo_path)
        
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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "agent": "AGENT NEO",
        "version": "1.0.0",
        "status": "Working",
        "endpoints": {
            "health": "/health",
            "plan": "/plan",
            "execute": "/execute"
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

