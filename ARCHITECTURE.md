# Architecture Notes
## Configurable Workflow Decision System

Author: Arpan Narula

## 1. Problem Framing

The assignment is not just about returning approved or rejected responses. The harder part is building something that can survive changing workflow requirements without turning into a pile of hardcoded if-statements.

The system therefore needs to do five things well:

- accept structured requests
- run configurable rules and stages
- preserve state and audit history
- handle failures and retries safely
- stay easy to change when the workflow definition changes

## 2. High-Level Design

```text
Client request
    |
    v
FastAPI layer
    |
    +--> idempotency lookup
    |
    v
Workflow engine
    |
    +--> validation stage
    +--> external dependency stage
    +--> rules stage
    +--> optional AI review stage
    +--> final decision stage
    |
    v
SQLite state + idempotency cache
    |
    v
Audit trail returned in API response
```

## 3. Main Components

### 3.1 API Layer

`app/main.py` owns the HTTP surface:

- request validation through Pydantic
- response serialization
- idempotency replay handling
- workflow status and audit endpoints
- config reload endpoint

It deliberately does not own workflow logic.

### 3.2 Workflow Engine

`app/workflow_engine.py` is the orchestrator.

It loads the workflow definition, executes stages in order, records intermediate state, and applies retry behavior when an external dependency fails. The retry is done at the engine level so failure handling stays consistent.

### 3.3 Rules Engine

`app/rules_engine.py` evaluates workflow rules from YAML.

Important implementation detail: this now uses a restricted AST parser rather than `eval()`. That means the config can still express readable conditions like:

- `data.age >= 18`
- `data.loan_amount <= data.monthly_income * 10`
- `data.employment_status in ['employed', 'self_employed']`

but it does not execute arbitrary Python from the config file.

### 3.4 State Manager

`app/state_manager.py` stores:

- workflow lifecycle state
- stage history
- audit trail
- idempotency cache

SQLite is enough for this assignment and keeps the project runnable without extra services.

### 3.5 External Dependency Simulation

`app/external_deps.py` simulates a downstream check with:

- artificial latency
- random failure rate
- deterministic credit-score generation per applicant name

That makes retry behavior observable while keeping tests reproducible.

### 3.6 Optional AI Review

`app/ai_agent.py` is treated as an optional review stage, not the source of truth.

The rule engine always establishes a preliminary decision first. If AI review is enabled and configured, it can add a second-pass explanation and optionally adjust the decision. If it is disabled or unavailable, the system falls back to the rule-based result without failing the workflow.

That design keeps the core system explainable even when the AI integration is off.

## 4. Data Flow Example

Example loan request:

1. Request reaches `POST /workflow/submit`.
2. The API checks whether the `request_id` already exists in the idempotency cache.
3. The workflow engine loads `config/workflows/loan_approval.yaml`.
4. Validation confirms required fields are present.
5. The external dependency stage simulates a credit bureau lookup.
6. The rules stage evaluates configured conditions and derives a preliminary decision.
7. The AI review stage either:
   - runs an optional second-pass review, or
   - returns a rule-based fallback explanation if disabled or unavailable.
8. The final stage records the decision.
9. State and audit history are returned in the response and cached for duplicate requests.

## 5. Key Design Choices

### YAML For Workflow Definitions

This was chosen because the assignment explicitly emphasizes change tolerance. YAML keeps workflow structure visible and easy to edit. It also makes the rule-change demonstration straightforward.

Trade-off:

- good for assignment clarity and version control
- not as friendly as a real admin UI

### SQLite For State

SQLite gives persistence with very low setup cost.

Trade-off:

- excellent for a local assignment submission
- not the final choice for high-concurrency production use

### Rule-First, AI-Second

The project treats rules as the primary decision mechanism and AI as optional review. That choice was intentional:

- rules are deterministic and easy to audit
- AI can add explanation or nuance
- the system still works when AI review is unavailable

### Retry At The Workflow Level

External dependency failures are retried from the engine layer rather than hiding retry logic inside individual dependency calls. That keeps behavior centralized and easier to reason about.

## 6. How Requirement Changes Are Handled

The assignment explicitly says the system must tolerate requirement changes.

This project handles that by keeping business logic in config:

- add a new workflow by adding a new YAML file
- change a threshold by editing a rule condition
- change AI usage by toggling the AI stage config
- reload a workflow without restarting the server

The `test_rule_change.py` file is there to prove this behavior rather than only describing it.

## 7. Failure Handling

The system handles several failure classes:

- bad request body -> FastAPI/Pydantic returns `422`
- unknown workflow type -> `404`
- external dependency failure after retries -> `503`
- duplicate request id -> cached response replay
- AI unavailable -> rule-based fallback

The goal is to degrade in a predictable way rather than fail silently.

## 8. Scaling Path

If this project were extended beyond the assignment, the next upgrades would be:

- PostgreSQL for shared state
- queue-based or async processing for longer workflows
- structured metrics and tracing
- proper auth around audit and admin endpoints
- managed config storage instead of local files

## 9. Assumptions

- One request maps to one workflow instance.
- YAML files are controlled by trusted operators.
- SQLite is acceptable for the assignment environment.
- AI review is useful but not required for the system to function.
