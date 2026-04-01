# Architecture Document
## AI Workflow Decision Platform

**Author:** Arpan Narula | 2022UCI8004 | NSUT Delhi

---

## 1. Problem Understanding

The core challenge: build a system that processes business requests through configurable rules, tolerates dependency failures, never processes the same request twice, and explains every decision. The "configurable" requirement is the tricky part - it rules out any approach that hardcodes business logic in Python.

The system needs to work for loan approvals today and employee onboarding tomorrow, without engineering involvement for each new workflow type.

---

## 2. System Overview

```
Client Request
      |
      v
[FastAPI Layer]  <-- validates schema, checks idempotency cache
      |
      v
[Workflow Engine]  <-- reads stage list from YAML config
      |
      +---> [Validation Stage]      checks required fields
      |
      +---> [External Dep Stage]    calls credit bureau (with retry)
      |
      +---> [Rules Engine Stage]    evaluates YAML conditions
      |
      +---> [AI Agent Stage]        Gemini second-pass review
      |
      +---> [Decision Stage]        final status
      |
      v
[State Manager]  <-- persists every stage to SQLite
      |
      v
[Audit Logger]   <-- records every event with timestamps
      |
      v
Response to Client (with decision + audit trail)
```

---

## 3. Component Breakdown

### 3.1 FastAPI Layer (`app/main.py`)

The HTTP interface. Handles:
- Request deserialization via Pydantic
- Idempotency check before any processing starts
- Error mapping (FileNotFoundError -> 404, ExternalDependencyError -> 503)
- Config hot-reload endpoint

No business logic lives here. It delegates immediately to the workflow engine.

### 3.2 Workflow Engine (`app/workflow_engine.py`)

The orchestrator. Reads a workflow's stage list from config and runs each stage in sequence. Wraps everything in retry logic for external dependency failures.

Key decisions:
- Retry is at the engine level, not inside individual stages. This means any stage can raise `ExternalDependencyError` and the entire workflow retries cleanly from the beginning, preserving state consistency.
- Each stage writes to SQLite before moving to the next. If the process dies mid-workflow, state is not lost.

### 3.3 Rules Engine (`app/rules_engine.py`)

Evaluates string conditions from YAML against a context dict. Supports `>=`, `<=`, `>`, `<`, `==`, `!=`, and `in` operators. Handles dotted path resolution (`data.age`, `external.credit_score`) and simple arithmetic on the right-hand side (`data.monthly_income * 10`).

No `eval()` on user input - expressions are parsed structurally and values are resolved from a controlled context dict.

### 3.4 AI Agent (`app/ai_agent.py`)

Sends the full application context - raw data, external data, rule results, preliminary decision - to Gemini 1.5 Flash. The model returns a structured JSON with final decision, confidence score, plain English reasoning, key factors, and risk flags.

The AI layer can override the rule-based preliminary decision. This catches edge cases rules miss - for example, a borderline credit score combined with unusually high income, or an applicant whose loan purpose suggests elevated risk beyond what numeric thresholds detect.

If Gemini is unavailable, `_rule_based_fallback()` takes over and the system continues without AI. No silent degradation.

### 3.5 State Manager (`app/state_manager.py`)

SQLite with two tables:
- `workflow_states` - full lifecycle state per request. Updated after every stage.
- `idempotency_cache` - stores completed responses keyed by request_id. Any duplicate request hits this first and returns immediately without reprocessing.

### 3.6 Config Loader (`app/config_loader.py`)

Reads YAML files from `config/workflows/`. In-memory cache after first load. Hot-reload clears the cache for a specific workflow type - the next request picks up the new config. No restart needed.

### 3.7 External Dependencies (`app/external_deps.py`)

Mock credit bureau with:
- Realistic latency (50-300ms random sleep)
- 15% random failure rate to exercise retry logic
- Deterministic scores based on applicant name hash (reproducible in tests)
- Separate `force_fail` flag for tests

In production, replace the implementation of `get_credit_score()`. The rest of the system does not change.

---

## 4. Data Flow - Loan Approval

```
POST /workflow/submit
  {request_id: "loan-001", workflow_type: "loan_approval", data: {...}}
  
  -> Idempotency check: loan-001 seen before? No -> proceed
  -> Load config/workflows/loan_approval.yaml
  -> Stage 1 [validation]: required fields present? Yes -> pass
  -> Stage 2 [external_dependency]: call credit bureau
       Attempt 1: timeout -> retry (2s backoff)
       Attempt 2: success, credit_score=720
  -> Stage 3 [rules]: evaluate 7 conditions
       age_min: 30 >= 18 -> PASS
       min_income: 80000 >= 25000 -> PASS
       credit_score_threshold: 720 >= 600 -> PASS
       loan_to_income_ratio: 500000 <= 800000 -> PASS
       employment_check: 'employed' in [...] -> PASS
       existing_loans_limit: 0 <= 3 -> PASS
       preliminary_decision: approved
  -> Stage 4 [ai_agent]: send full context to Gemini
       AI confirms: approved, confidence: 92
       reasoning: "Strong profile, low debt, stable employment..."
  -> Stage 5 [decision]: final status = approved
  -> Save idempotency cache
  
Response: status=approved, all rules, AI reasoning, full audit trail
```

---

## 5. Key Design Decisions and Trade-offs

### Decision 1: YAML over database-stored config

YAML files are version-controllable, human-readable, and editable without a database client. The trade-off is that they're flat files - no UI for non-technical users to edit rules. For this assignment, YAML is the right call. In production, a database-backed config with a UI would be the next step.

### Decision 2: SQLite over in-memory state

An in-memory dict would be simpler, but it does not survive process restarts and cannot support multi-worker deployments. SQLite adds minimal complexity and gives us persistence and idempotency for free. The swap to PostgreSQL is straightforward when needed.

### Decision 3: AI as a second-pass reviewer, not the primary decision maker

Rules run first. AI reviews after. This keeps decisions auditable and deterministic for clear-cut cases while allowing the AI to catch nuance in borderline situations. A pure LLM approach would make audit trails harder to generate and decisions less reproducible.

### Decision 4: Retry at workflow level, not stage level

When the credit bureau fails, the entire workflow retries from scratch. This is simpler than per-stage retry and avoids partial state inconsistencies where some stages succeeded and others did not.

### Decision 5: Synchronous execution

Sync is simpler to debug and trace. For a hackathon context with moderate load, it's the right call. The architecture does not preclude async - `workflow_engine.py` could be converted to async with `asyncio` and FastAPI's background tasks for production use.

---

## 6. Configurability - How It Works

A workflow is entirely defined by its YAML file. Adding a new workflow:
1. Create `config/workflows/new_type.yaml`
2. Define stages, rules, and retry settings
3. Submit a request with `workflow_type: "new_type"`

Changing a rule:
1. Edit the YAML condition
2. POST `/config/reload/workflow_type`
3. Done - next request uses the new rule

No Python code changes required for either operation.

---

## 7. Failure Handling Summary

| Failure Type | Handling |
|-------------|---------|
| Invalid request schema | Pydantic returns HTTP 422 with field details |
| Unknown workflow type | HTTP 404 with clear message |
| External dep timeout | Retry up to 3x with exponential backoff |
| All retries exhausted | HTTP 503 - never a silent failure |
| AI agent unavailable | Rule-based fallback, no crash |
| Duplicate request_id | Return cached response, skip reprocessing |
| DB write failure | Exception propagates, HTTP 500 returned |

---

## 8. Scaling Considerations

| Layer | Current | Production Path |
|-------|---------|-----------------|
| Database | SQLite | PostgreSQL with connection pooling |
| Workers | Single uvicorn | Multiple workers behind nginx or a load balancer |
| Config storage | YAML files | DB table or object storage (S3/GCS) |
| AI calls | Synchronous | Async with queued background processing |
| External deps | Mock | Real API clients with circuit breakers |
| Audit logs | SQLite table | Structured logging to ELK or CloudWatch |

The interfaces between components are stable. Swapping the implementation behind any of them does not require changes elsewhere.

---

## 9. Assumptions

- One workflow request maps to one applicant and one decision. Batch processing is out of scope.
- The credit bureau is the only external dependency demonstrated. The pattern in `external_deps.py` extends to any number of services.
- Gemini API availability is assumed for normal operation. Degraded-mode (rule-only) decisions are flagged in the reviewer note field.
- SQLite file is co-located with the application. In a containerized deployment, this would be a mounted volume or replaced with a remote DB.
