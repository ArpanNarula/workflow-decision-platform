"""
Retry + dependency failure: force external dep to fail, verify retry behaviour and error response.
"""
import uuid
from unittest.mock import patch
from app.external_deps import ExternalDependencyError


def test_external_dep_failure_returns_503(client):
    """If all retry attempts fail, API must return 503 - not 500."""
    with patch("app.workflow_engine.get_credit_score", side_effect=ExternalDependencyError("Timeout")):
        resp = client.post("/workflow/submit", json={
            "request_id": f"retry-fail-{uuid.uuid4()}",
            "workflow_type": "loan_approval",
            "applicant_name": "Retry Test",
            "data": {
                "age": 28,
                "monthly_income": 60000,
                "loan_amount": 300000,
                "employment_status": "employed",
                "existing_loans": 0
            }
        })
    assert resp.status_code == 503
    assert "External service unavailable" in resp.json()["detail"]


def test_external_dep_succeeds_on_second_attempt(client):
    """Transient failure then success = workflow completes normally."""
    call_count = {"n": 0}

    def flaky_credit_score(name, force_fail=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ExternalDependencyError("First attempt timeout")
        # Real import to get actual mock data
        from app.external_deps import get_credit_score as real_fn
        import unittest.mock as m
        # Return a fake score on second attempt
        return {
            "provider": "MockCreditBureau v2",
            "applicant_name": name,
            "credit_score": 720,
            "credit_age_months": 36,
            "active_accounts": 2,
            "defaults_last_2_years": 0,
            "retrieved_at": 0,
            "status": "success"
        }

    with patch("app.workflow_engine.get_credit_score", side_effect=flaky_credit_score):
        resp = client.post("/workflow/submit", json={
            "request_id": f"retry-ok-{uuid.uuid4()}",
            "workflow_type": "loan_approval",
            "applicant_name": "Flaky Test User",
            "data": {
                "age": 30,
                "monthly_income": 70000,
                "loan_amount": 400000,
                "employment_status": "employed",
                "existing_loans": 1
            }
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["approved", "manual_review", "rejected"]
    # Should have taken at least 2 attempts
    assert call_count["n"] >= 2
