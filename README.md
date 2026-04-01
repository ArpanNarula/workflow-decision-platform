# AI Workflow Decision Platform

**Author:** Arpan Narula | 2022UCI8004 | NSUT Delhi  
**Stack:** Python 3.11, FastAPI, SQLite, Gemini 1.5 Flash  
**Assignment:** Resilient Decision System - Hackathon

---

## What This Is

A configurable workflow engine that processes business requests - loan approvals, onboarding, vendor checks - through a multi-stage pipeline. Rules live in YAML files. An AI agent (Gemini) reviews every decision beyond what hard rules can catch. The system handles retries, duplicate requests, and full audit trails out of the box.

You can add a new workflow type, or change an existing rule, without touching any Python code.

---

## Quickstart

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Add your Gemini API key to .env (already set)
# GEMINI_API_KEY=your_key_here

# 3. Start the server
python3 -m uvicorn app.main:app --reload --port 8000

# 4. Open API docs
open http://localhost:8000/docs

# 5. Run tests
pytest tests/ -v
```

---

## Try It - Submit a Loan Application

```bash
curl -X POST http://localhost:8000/workflow/submit \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "loan-demo-001",
    "workflow_type": "loan_approval",
    "applicant_name": "Rahul Sharma",
    "data": {
      "age": 30,
      "monthly_income": 80000,
      "loan_amount": 500000,
      "employment_status": "employed",
      "existing_loans": 0
    }
  }'
```

You get back: final decision, every rule that was evaluated, AI reasoning in plain English, and a full audit trail.

---

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health + available workflows |
| GET | `/docs` | Interactive Swagger UI |
| POST | `/workflow/submit` | Submit a workflow request |
| GET | `/workflow/{id}/status` | Check current status |
| GET | `/workflow/{id}/audit` | Full explainable audit trail |
| GET | `/workflows` | List configured workflow types |
| POST | `/config/reload/{type}` | Hot-reload YAML config (no restart) |

---

## Project Structure

```
workflow-decision-platform/
├── app/
│   ├── main.py              # FastAPI app + all endpoints
│   ├── models.py            # Pydantic request/response models
│   ├── workflow_engine.py   # Stage orchestration + retry logic
│   ├── rules_engine.py      # YAML condition evaluator
│   ├── ai_agent.py          # Gemini AI decision layer
│   ├── state_manager.py     # SQLite persistence + idempotency cache
│   ├── config_loader.py     # YAML loader with hot-reload
│   ├── audit_logger.py      # Structured audit trail
│   └── external_deps.py     # Mock credit bureau (simulates failures)
├── config/
│   └── workflows/
│       ├── loan_approval.yaml       # Full loan workflow config
│       └── employee_onboarding.yaml # Onboarding workflow config
├── tests/
│   ├── conftest.py           # Shared fixtures
│   ├── test_happy_path.py    # Valid inputs, expected decisions
│   ├── test_invalid_input.py # Bad data, missing fields, wrong types
│   ├── test_duplicate.py     # Idempotency verification
│   ├── test_retry.py         # External dep failures + retry
│   └── test_rule_change.py   # YAML rule change without restart
├── examples/
│   └── decision_examples.json  # Sample inputs + expected outputs
├── .env                     # API keys
└── requirements.txt
```

---

## How to Add a New Workflow

No Python code needed. Create a YAML file:

```bash
touch config/workflows/vendor_approval.yaml
```

```yaml
workflow:
  name: vendor_approval
  version: "1.0"

stages:
  - name: schema_validation
    type: validation
    required_fields: [company_name, annual_revenue, years_in_business]

  - name: rule_evaluation
    type: rules
    rules:
      - id: min_revenue
        description: Annual revenue must exceed Rs. 10 lakh
        condition: "data.annual_revenue >= 1000000"
        on_fail: reject

      - id: min_years
        description: Company must be at least 2 years old
        condition: "data.years_in_business >= 2"
        on_fail: manual_review

  - name: ai_decision
    type: ai_agent

  - name: final_decision
    type: decision

retry:
  max_attempts: 3
  backoff_seconds: 2
```

Then reload (no restart):

```bash
curl -X POST http://localhost:8000/config/reload/vendor_approval
```

Submit a vendor request and it works immediately.

---

## Changing Existing Rules (No Restart)

Edit `config/workflows/loan_approval.yaml` - for example, tighten the credit score threshold:

```yaml
- id: credit_score_threshold
  description: Credit score must be 700 or above  # was 600
  condition: "external.credit_score >= 700"        # changed
  on_fail: reject
```

Then:

```bash
curl -X POST http://localhost:8000/config/reload/loan_approval
```

All subsequent requests use the new rule. No code change, no restart.

---

## Idempotency

Send the same `request_id` twice - you get the same response, the workflow does not run again, and the response header `X-Idempotent-Replay: true` is set. This handles network retries and accidental duplicate submissions safely.

---

## Retry Logic

The credit bureau mock fails ~15% of the time (configurable). The engine retries up to 3 times with exponential backoff (2s, 4s). If all attempts fail, the API returns HTTP 503 with a clear error. No silent failures.

---

## Running Tests

```bash
pytest tests/ -v

# Run a specific test file
pytest tests/test_rule_change.py -v

# With coverage
pytest tests/ --tb=short
```

Expected: 20+ test cases covering happy path, invalid input, duplicate requests, retry failures, and live rule changes.

---

## Scaling Notes

- **State store:** SQLite works fine for this demo. In production, swap for PostgreSQL (change 3 lines in `state_manager.py`).
- **AI layer:** Gemini calls are synchronous here. At scale, move to async with `asyncio` + connection pooling.
- **Config store:** YAMLs can move to a database table or S3 bucket - the `config_loader.py` interface stays the same.
- **Workers:** FastAPI + uvicorn support multi-worker deployments with `--workers 4`. State in SQLite/Postgres handles concurrency safely.
- **Rule engine:** Current evaluator handles standard comparisons. A more complex DSL (e.g. using `lark`) can extend it without touching workflow logic.
