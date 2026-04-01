import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from app.models import WorkflowRequest, WorkflowResponse
from app.state_manager import init_db, get_state, save_idempotency_response, get_idempotency_response
from app.workflow_engine import execute_workflow
from app.config_loader import list_available_workflows, reload_workflow_config
from app.external_deps import ExternalDependencyError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

init_db()

app = FastAPI(
    title="AI Workflow Decision Platform",
    description=(
        "A configurable, AI-powered workflow engine. Rules and stages are defined in YAML. "
        "Gemini AI provides an intelligent second-pass review beyond hard rules. "
        "Supports idempotency, retries, full audit trails, and hot config reload."
    ),
    version="1.0.0",
    contact={"name": "Arpan Narula", "email": "arpannarula9999@gmail.com"}
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "AI Workflow Decision Platform",
        "version": "1.0.0",
        "author": "Arpan Narula | 2022UCI8004 | NSUT Delhi",
        "docs": "/docs",
        "available_workflows": list_available_workflows()
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/workflows", tags=["Config"])
def list_workflows():
    """List all configured workflow types."""
    workflows = list_available_workflows()
    return {"workflows": workflows, "count": len(workflows)}


@app.post("/workflow/submit", response_model=WorkflowResponse, tags=["Workflow"])
def submit_workflow(request: WorkflowRequest):
    """
    Submit a new workflow request for AI-powered evaluation.

    - **Idempotent**: sending the same `request_id` twice returns the cached result.
    - **Retries**: external dependency failures are retried automatically (up to 3x).
    - **AI decision**: Gemini reviews beyond raw rule checks.
    - **Full audit trail** included in response.
    """
    logger.info("Incoming request: %s | type=%s", request.request_id, request.workflow_type)

    # Idempotency - return cached response if request_id already processed
    cached = get_idempotency_response(request.request_id)
    if cached:
        logger.info("Idempotent replay for: %s", request.request_id)
        return JSONResponse(
            content=cached,
            headers={"X-Idempotent-Replay": "true", "X-Request-Id": request.request_id}
        )

    try:
        response = execute_workflow(request)
        response_dict = response.model_dump(mode="json")
        save_idempotency_response(request.request_id, response_dict)
        return response

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExternalDependencyError as e:
        raise HTTPException(status_code=503, detail=f"External service unavailable after retries: {e}")
    except Exception as e:
        logger.exception("Unhandled error in workflow execution")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/{request_id}/status", tags=["Workflow"])
def get_status(request_id: str):
    """Get current status and stage of a workflow by request_id."""
    state = get_state(request_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No workflow found: {request_id}")
    return {
        "request_id": state.request_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "attempt_count": state.attempt_count,
        "created_at": state.created_at,
        "updated_at": state.updated_at
    }


@app.get("/workflow/{request_id}/audit", tags=["Audit"])
def get_audit(request_id: str):
    """
    Retrieve the full, explainable audit trail for a workflow.
    Every stage transition and rule evaluation is logged with timestamps.
    """
    state = get_state(request_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No workflow found: {request_id}")
    return {
        "request_id": request_id,
        "final_status": state.status,
        "audit_trail": state.audit_trail,
        "stage_count": len(state.stage_history)
    }


@app.post("/config/reload/{workflow_type}", tags=["Config"])
def reload_config(workflow_type: str):
    """
    Hot-reload a workflow YAML config without restarting the server.
    Edit the YAML file, then call this endpoint to apply changes immediately.
    """
    try:
        cfg = reload_workflow_config(workflow_type)
        return {
            "message": f"Config reloaded: {workflow_type}",
            "version": cfg.get("workflow", {}).get("version", "unknown")
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No config found for: {workflow_type}")
