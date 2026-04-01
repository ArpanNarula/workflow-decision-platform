"""
Invalid input and non-approved decision paths.
"""

import uuid


def test_unknown_workflow_type(client):
    resp = client.post(
        "/workflow/submit",
        json={
            "request_id": f"test-{uuid.uuid4()}",
            "workflow_type": "nonexistent_workflow",
            "applicant_name": "Test User",
            "data": {"age": 25},
        },
    )
    assert resp.status_code == 404


def test_underage_applicant_is_rejected(client, rejected_loan_request):
    resp = client.post("/workflow/submit", json=rejected_loan_request)
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"] == "rejected"

    age_rule = next(rule for rule in data["rules_triggered"] if rule["rule_id"] == "age_min")
    assert age_rule["passed"] is False


def test_unemployed_applicant_is_rejected(client):
    resp = client.post(
        "/workflow/submit",
        json={
            "request_id": f"test-{uuid.uuid4()}",
            "workflow_type": "loan_approval",
            "applicant_name": "No Job Person",
            "data": {
                "age": 28,
                "monthly_income": 5000,
                "loan_amount": 1000000,
                "employment_status": "unemployed",
                "existing_loans": 0,
            },
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"] == "rejected"


def test_high_loan_ratio_goes_to_manual_review(client, monkeypatch):
    def medium_risk_credit_score(applicant_name: str, force_fail: bool = False):
        return {
            "provider": "MockCreditBureau v2",
            "applicant_name": applicant_name,
            "credit_score": 680,
            "credit_age_months": 36,
            "active_accounts": 2,
            "defaults_last_2_years": 0,
            "retrieved_at": 0,
            "status": "success",
        }

    monkeypatch.setattr("app.workflow_engine.get_credit_score", medium_risk_credit_score)

    resp = client.post(
        "/workflow/submit",
        json={
            "request_id": f"manual-review-{uuid.uuid4()}",
            "workflow_type": "loan_approval",
            "applicant_name": "Manual Review Case",
            "data": {
                "age": 35,
                "monthly_income": 45000,
                "loan_amount": 500000,
                "employment_status": "self_employed",
                "existing_loans": 2,
            },
        },
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "manual_review"
    assert data["decision"] == "manual_review"
    assert any(
        rule["rule_id"] == "loan_to_income_ratio" and rule["passed"] is False
        for rule in data["rules_triggered"]
    )


def test_missing_required_body_fields(client):
    resp = client.post("/workflow/submit", json={})
    assert resp.status_code == 422


def test_status_for_nonexistent_request(client):
    resp = client.get("/workflow/does-not-exist/status")
    assert resp.status_code == 404


def test_audit_for_nonexistent_request(client):
    resp = client.get("/workflow/does-not-exist/audit")
    assert resp.status_code == 404
