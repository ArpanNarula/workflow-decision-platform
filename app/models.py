from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"


class RuleResult(BaseModel):
    rule_id: str
    description: str
    passed: bool
    value_evaluated: Any = None
    on_fail_action: str = "reject"


class StageResult(BaseModel):
    stage_name: str
    status: str
    rules_results: List[RuleResult] = []
    ai_reasoning: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkflowRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str
    applicant_name: str
    data: Dict[str, Any]

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req-loan-001",
                "workflow_type": "loan_approval",
                "applicant_name": "Rahul Sharma",
                "data": {
                    "age": 28,
                    "monthly_income": 75000,
                    "loan_amount": 500000,
                    "employment_status": "employed",
                    "loan_purpose": "home renovation",
                    "existing_loans": 0
                }
            }
        }
    }


class WorkflowResponse(BaseModel):
    request_id: str
    workflow_type: str
    applicant_name: str
    status: WorkflowStatus
    decision: str
    ai_reasoning: str
    rules_triggered: List[RuleResult]
    stage_history: List[StageResult]
    audit_trail: List[Dict[str, Any]]
    processing_time_ms: float
    timestamp: datetime


class WorkflowState(BaseModel):
    request_id: str
    workflow_type: str
    applicant_name: str
    status: WorkflowStatus
    current_stage: str
    data: Dict[str, Any]
    stage_history: List[Any] = []
    audit_trail: List[Dict[str, Any]] = []
    attempt_count: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
