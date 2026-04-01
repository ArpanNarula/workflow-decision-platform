import time
import logging
from datetime import datetime
from typing import Dict, Any, Tuple

from app.models import (
    WorkflowRequest, WorkflowResponse, WorkflowState,
    WorkflowStatus, StageResult, RuleResult
)
from app.config_loader import load_workflow_config
from app.rules_engine import evaluate_rules, get_decision_from_rules
from app.state_manager import save_state
from app.audit_logger import create_audit_entry
from app.external_deps import get_credit_score, ExternalDependencyError
from app.ai_agent import analyze_application

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "approved": WorkflowStatus.APPROVED,
    "rejected": WorkflowStatus.REJECTED,
    "manual_review": WorkflowStatus.MANUAL_REVIEW,
}


def execute_workflow(request: WorkflowRequest) -> WorkflowResponse:
    """
    Entry point. Wraps the core workflow with retry logic.
    Retries on ExternalDependencyError with exponential backoff.
    """
    config = load_workflow_config(request.workflow_type)
    retry_cfg = config.get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 3)
    backoff = retry_cfg.get("backoff_seconds", 2)

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Workflow attempt %d/%d for request: %s", attempt, max_attempts, request.request_id)
            return _run_workflow(request, config, attempt)
        except ExternalDependencyError as e:
            last_error = e
            logger.warning("Attempt %d failed - external dep error: %s", attempt, e)
            if attempt < max_attempts:
                sleep = backoff ** attempt
                logger.info("Retrying in %ss...", sleep)
                time.sleep(sleep)

    raise last_error


def _run_workflow(request: WorkflowRequest, config: Dict, attempt: int) -> WorkflowResponse:
    start_ms = time.time()
    stages = config.get("stages", [])

    state = WorkflowState(
        request_id=request.request_id,
        workflow_type=request.workflow_type,
        applicant_name=request.applicant_name,
        status=WorkflowStatus.IN_PROGRESS,
        current_stage="init",
        data=request.data,
        attempt_count=attempt,
    )
    state.audit_trail.append(create_audit_entry(
        "workflow_started", "init",
        {"workflow_type": request.workflow_type, "attempt": attempt}
    ))
    save_state(state)

    external_data: Dict[str, Any] = {}
    rule_results: list = []
    ai_result: Dict = {}
    final_decision = "pending"

    for stage in stages:
        stage_name = stage.get("name")
        stage_type = stage.get("type")
        state.current_stage = stage_name

        logger.info("--- Stage: %s [%s] ---", stage_name, stage_type)

        if stage_type == "validation":
            stage_result = _stage_validate(request, stage)

        elif stage_type == "external_dependency":
            # This can raise ExternalDependencyError - caught by execute_workflow
            stage_result, external_data = _stage_external(request, stage, external_data)

        elif stage_type == "rules":
            context = {"data": request.data, "external": external_data}
            rule_results = evaluate_rules(stage.get("rules", []), context)
            preliminary = get_decision_from_rules(rule_results)
            stage_result = StageResult(
                stage_name=stage_name,
                status=preliminary,
                rules_results=rule_results
            )

        elif stage_type == "ai_agent":
            preliminary = get_decision_from_rules(rule_results) if rule_results else "manual_review"
            ai_result = analyze_application(
                request.workflow_type,
                request.data,
                rule_results,
                external_data,
                preliminary,
                stage,
            )
            final_decision = ai_result.get("final_decision", preliminary)
            stage_result = StageResult(
                stage_name=stage_name,
                status=final_decision,
                ai_reasoning=ai_result.get("reasoning", "")
            )

        elif stage_type == "decision":
            stage_result = StageResult(stage_name=stage_name, status=final_decision)

        else:
            logger.warning("Unknown stage type: %s, skipping", stage_type)
            continue

        state.stage_history.append(stage_result)
        state.audit_trail.append(create_audit_entry(
            f"stage_complete", stage_name,
            {"status": stage_result.status, "type": stage_type},
            status="success"
        ))
        save_state(state)

    # If ai_agent stage was skipped for some reason, fall back to rules
    if final_decision == "pending":
        final_decision = get_decision_from_rules(rule_results) if rule_results else "manual_review"

    state.status = _STATUS_MAP.get(final_decision, WorkflowStatus.MANUAL_REVIEW)
    state.audit_trail.append(create_audit_entry(
        "workflow_complete", "final",
        {
            "decision": final_decision,
            "confidence": ai_result.get("confidence", "N/A"),
            "attempt": attempt
        },
        status="completed"
    ))
    save_state(state)

    elapsed = round((time.time() - start_ms) * 1000, 2)

    return WorkflowResponse(
        request_id=request.request_id,
        workflow_type=request.workflow_type,
        applicant_name=request.applicant_name,
        status=state.status,
        decision=final_decision,
        ai_reasoning=ai_result.get("reasoning", "Decision based on rule evaluation only."),
        rules_triggered=rule_results,
        stage_history=state.stage_history,
        audit_trail=state.audit_trail,
        processing_time_ms=elapsed,
        timestamp=datetime.utcnow()
    )


def _stage_validate(request: WorkflowRequest, stage: Dict) -> StageResult:
    required = stage.get("required_fields", [])
    missing = [f for f in required if f not in request.data or request.data[f] is None]
    return StageResult(
        stage_name=stage["name"],
        status="failed" if missing else "passed",
        ai_reasoning=f"Missing fields: {missing}" if missing else "All required fields present"
    )


def _stage_external(
    request: WorkflowRequest, stage: Dict, external_data: Dict
) -> Tuple[StageResult, Dict]:
    dep = stage.get("dependency", "credit_bureau")
    logger.info("Calling external dependency: %s", dep)

    credit = get_credit_score(request.applicant_name)
    external_data["credit_score"] = credit["credit_score"]
    external_data["credit_bureau"] = credit

    return StageResult(
        stage_name=stage["name"],
        status="success",
        ai_reasoning=f"Credit score retrieved: {credit['credit_score']}"
    ), external_data
