import logging
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config_loader import list_available_workflows, reload_workflow_config
from app.external_deps import ExternalDependencyError
from app.models import WorkflowRequest, WorkflowResponse
from app.state_manager import (
    get_idempotency_response,
    get_state,
    init_db,
    save_idempotency_response,
)
from app.workflow_engine import execute_workflow

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

init_db()

app = FastAPI(
    title="Configurable Workflow Decision System",
    description=(
        "A configurable workflow service built for the resilient decision system assignment. "
        "Rules and stages live in YAML, workflow state is stored in SQLite, and the API "
        "supports retries, idempotency, audit trails, and optional AI review."
    ),
    version="1.0.0",
    contact={"name": "Arpan Narula", "email": "arpannarula9999@gmail.com"},
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _render_homepage(workflows: list[str]) -> str:
    workflow_items = "".join(f"<li>{workflow}</li>" for workflow in workflows)
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Configurable Workflow Decision System</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f4efe6;
        --ink: #1e2430;
        --muted: #5f6b7a;
        --card: rgba(255, 252, 247, 0.86);
        --line: rgba(30, 36, 48, 0.14);
        --accent: #b6542c;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(182, 84, 44, 0.12), transparent 28%),
          radial-gradient(circle at bottom right, rgba(38, 90, 118, 0.12), transparent 22%),
          var(--bg);
      }}
      main {{
        max-width: 980px;
        margin: 0 auto;
        padding: 48px 20px 56px;
      }}
      .hero {{
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: var(--card);
        box-shadow: 0 18px 40px rgba(32, 38, 45, 0.08);
      }}
      .eyebrow {{
        letter-spacing: 0.12em;
        text-transform: uppercase;
        font-family: "Helvetica Neue", Arial, sans-serif;
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 12px;
      }}
      h1 {{
        margin: 0 0 14px;
        font-size: clamp(2rem, 5vw, 3.5rem);
        line-height: 1.05;
      }}
      p {{
        margin: 0;
        font-size: 1.05rem;
        line-height: 1.7;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 16px;
        margin-top: 22px;
      }}
      .card {{
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        background: rgba(255, 255, 255, 0.72);
      }}
      .card h2 {{
        margin: 0 0 8px;
        font-size: 1.1rem;
        font-family: "Helvetica Neue", Arial, sans-serif;
      }}
      .card p, .card li {{
        font-size: 0.98rem;
        color: var(--muted);
      }}
      a {{
        color: var(--accent);
        text-decoration: none;
      }}
      a:hover {{
        text-decoration: underline;
      }}
      code, pre {{
        font-family: "SFMono-Regular", Menlo, monospace;
      }}
      pre {{
        margin: 0;
        overflow-x: auto;
        white-space: pre-wrap;
        background: #1f2430;
        color: #f7f0e8;
        border-radius: 18px;
        padding: 18px;
      }}
      ul {{
        margin: 10px 0 0 18px;
        padding: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 18px;
      }}
      .button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 12px 16px;
        border-radius: 999px;
        border: 1px solid var(--accent);
        background: var(--accent);
        color: #fffaf5;
        font-family: "Helvetica Neue", Arial, sans-serif;
        font-size: 0.95rem;
      }}
      .button.secondary {{
        background: transparent;
        color: var(--accent);
      }}
      .section {{
        margin-top: 22px;
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <div class="eyebrow">Assignment Submission</div>
        <h1>Configurable Workflow Decision System</h1>
        <p>
          This is an API-first project for the resilient decision system assignment.
          It executes configurable workflows from YAML, keeps workflow state in SQLite,
          records audit history, retries dependency failures, and can optionally run an AI review step.
        </p>
        <div class="actions">
          <a class="button" href="/docs">Open API Docs</a>
          <a class="button secondary" href="/health">Health Check</a>
          <a class="button secondary" href="/workflows">Workflow List</a>
        </div>
      </section>

      <section class="grid section">
        <article class="card">
          <h2>Available Workflows</h2>
          <ul>{workflow_items}</ul>
        </article>
        <article class="card">
          <h2>What To Open</h2>
          <p>
            If you expected a browser UI, use <a href="/docs">/docs</a> for the interactive API explorer.
            The root page is just a quick project summary.
          </p>
        </article>
        <article class="card">
          <h2>Machine-Readable Info</h2>
          <p>
            Need JSON instead? Use <a href="/api-info">/api-info</a>,
            <a href="/health">/health</a>, or <a href="/workflows">/workflows</a>.
          </p>
        </article>
      </section>

      <section class="section">
        <pre>curl -X POST http://127.0.0.1:8000/workflow/submit \\
  -H "Content-Type: application/json" \\
  -d '{{"request_id":"demo-001","workflow_type":"loan_approval","applicant_name":"Ananya Singh","data":{{"age":30,"monthly_income":80000,"loan_amount":500000,"employment_status":"employed","existing_loans":0}}}}'</pre>
      </section>
    </main>
  </body>
</html>"""


@app.get("/", tags=["Health"], response_class=HTMLResponse)
def root():
    return HTMLResponse(_render_homepage(list_available_workflows()))


@app.get("/api-info", tags=["Health"])
def api_info():
    return {
        "service": "Configurable Workflow Decision System",
        "version": "1.0.0",
        "author": "Arpan Narula | 2022UCI8004 | NSUT Delhi",
        "docs": "/docs",
        "available_workflows": list_available_workflows(),
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
    Submit a new workflow request for evaluation.

    - **Idempotent**: sending the same `request_id` twice returns the cached result.
    - **Retries**: external dependency failures are retried automatically (up to 3x).
    - **AI review**: optional second-pass review can be enabled via config or environment.
    - **Full audit trail** included in response.
    """
    logger.info("Incoming request: %s | type=%s", request.request_id, request.workflow_type)

    cached = get_idempotency_response(request.request_id)
    if cached:
        logger.info("Idempotent replay for: %s", request.request_id)
        return JSONResponse(
            content=cached,
            headers={"X-Idempotent-Replay": "true", "X-Request-Id": request.request_id},
        )

    try:
        response = execute_workflow(request)
        response_dict = response.model_dump(mode="json")
        save_idempotency_response(request.request_id, response_dict)
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ExternalDependencyError as exc:
        raise HTTPException(status_code=503, detail=f"External service unavailable after retries: {exc}")
    except Exception as exc:
        logger.exception("Unhandled error in workflow execution")
        raise HTTPException(status_code=500, detail=str(exc))


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
        "updated_at": state.updated_at,
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
        "stage_count": len(state.stage_history),
    }


@app.post("/config/reload/{workflow_type}", tags=["Config"])
def reload_config(workflow_type: str):
    """
    Hot-reload a workflow YAML config without restarting the server.
    Edit the YAML file, then call this endpoint to apply changes immediately.
    """
    try:
        config = reload_workflow_config(workflow_type)
        return {
            "message": f"Config reloaded: {workflow_type}",
            "version": config.get("workflow", {}).get("version", "unknown"),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No config found for: {workflow_type}")
