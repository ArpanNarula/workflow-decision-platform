# Configurable Workflow Decision System

Submission for the "Design and Build a Resilient Decision System" hackathon assignment.

Author: Arpan Narula  
Stack: Python 3.11, FastAPI, SQLite, YAML-configured workflows, optional Gemini review

## What This Project Does

This service accepts structured workflow requests, runs them through configured stages, stores state as the workflow progresses, records an audit trail, and returns a final decision.

The implementation is intentionally configuration-driven. Workflow stages and rule definitions live in YAML files under `config/workflows/`, so changing a rule or adding a new workflow does not require a large code rewrite.

The current repo includes:

- `loan_approval`
- `employee_onboarding`

## Why It Matches The Assignment

The assignment asked for a system that can:

- accept and validate structured input
- evaluate business rules
- execute workflow stages including reject, retry, and manual review paths
- maintain state and history
- provide explainable audit information
- tolerate requirement changes
- simulate an external dependency
- support idempotency

This project covers those points with:

- FastAPI request handling and schema validation
- a YAML-driven workflow engine
- retry handling for a simulated downstream dependency
- SQLite-backed state tracking and idempotency caching
- audit logging for every workflow step
- tests for happy path, invalid input, duplicate request, retry flow, and rule change scenarios

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# add GEMINI_API_KEY only if you want AI review enabled

python3 -m uvicorn app.main:app --reload --port 8000
```

Open one of these:

- `http://127.0.0.1:8000/` for the landing page
- `http://127.0.0.1:8000/docs` for Swagger UI
- `http://127.0.0.1:8000/workflows` for the configured workflow list

If you do not want the AI review stage while testing locally, run:

```bash
ENABLE_AI_REVIEW=false python3 -m uvicorn app.main:app --reload --port 8000
```

## Example Request

```bash
curl -X POST http://127.0.0.1:8000/workflow/submit \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "loan-demo-001",
    "workflow_type": "loan_approval",
    "applicant_name": "Ananya Singh",
    "data": {
      "age": 30,
      "monthly_income": 80000,
      "loan_amount": 500000,
      "employment_status": "employed",
      "existing_loans": 0
    }
  }'
```

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Minimal landing page for local use |
| `GET` | `/api-info` | Machine-readable service summary |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive API docs |
| `GET` | `/workflows` | List configured workflow types |
| `POST` | `/workflow/submit` | Submit a workflow request |
| `GET` | `/workflow/{id}/status` | Inspect current status |
| `GET` | `/workflow/{id}/audit` | Retrieve audit trail |
| `POST` | `/config/reload/{type}` | Reload one workflow config |

## Project Layout

```text
workflow-decision-platform/
├── app/
│   ├── ai_agent.py
│   ├── audit_logger.py
│   ├── config_loader.py
│   ├── external_deps.py
│   ├── main.py
│   ├── models.py
│   ├── rules_engine.py
│   ├── state_manager.py
│   └── workflow_engine.py
├── config/
│   └── workflows/
├── examples/
├── tests/
├── .env.example
├── ARCHITECTURE.md
└── requirements.txt
```

## Configurability

Each workflow is defined by YAML:

- stage sequence
- required fields
- rule conditions
- failure actions
- retry settings
- whether the AI review stage is enabled

Example idea:

```yaml
- name: ai_decision
  type: ai_agent
  required: true
  enabled: true
  model: gemini-1.5-flash
```

If you want to disable AI review for a workflow, you can set `enabled: false` for that stage or use the environment variable `ENABLE_AI_REVIEW=false`.

## Notes On The Rules Engine

The rules engine uses a restricted AST parser instead of `eval()`. It supports:

- comparison operators like `>=`, `<=`, `==`, `!=`
- membership checks like `in`
- basic arithmetic such as `data.monthly_income * 10`
- boolean combinations with `and` and `or`

That keeps the rule format readable without executing arbitrary code from workflow files.

## Tests

Run the full suite with:

```bash
pytest tests/ -v
```

The tests cover:

- approved path
- manual review path
- invalid input
- duplicate request replay
- dependency retry behavior
- hot rule reload behavior
- safe rules-engine evaluation

## Scaling Notes

For the assignment, SQLite is enough and keeps the setup simple. If this were taken further, the first upgrades would be:

- PostgreSQL instead of SQLite
- background execution or async handling for long-running stages
- stronger auth and access control around audit endpoints
- dedicated config storage instead of local YAML files
- circuit breakers and metrics around external dependencies
