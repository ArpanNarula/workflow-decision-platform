"""
Invalid input: wrong workflow type, underage applicant, missing required fields.
"""
import uuid


def test_unknown_workflow_type(client):
    resp = client.post("/workflow/submit", json={
        "request_id": f"test-{uuid.uuid4()}",
        "workflow_type": "nonexistent_workflow",
        "applicant_name": "Test User",
        "data": {"age": 25}
    })
    assert resp.status_code == 404


def test_underage_applicant_fails(client, rejected_loan_request):
    resp = client.post("/workflow/submit", json=rejected_loan_request)
    assert resp.status_code == 200
    data = resp.json()
    # Rules should catch age < 18 as a hard reject
    assert data["status"] in ["rejected", "manual_review"]

    # Confirm age_min rule specifically failed
    age_rule = next((r for r in data["rules_triggered"] if r["rule_id"] == "age_min"), None)
    assert age_rule is not None
    assert age_rule["passed"] is False


def test_unemployed_applicant_rejected(client):
    resp = client.post("/workflow/submit", json={
        "request_id": f"test-{uuid.uuid4()}",
        "workflow_type": "loan_approval",
        "applicant_name": "No Job Person",
        "data": {
            "age": 28,
            "monthly_income": 5000,
            "loan_amount": 1000000,
            "employment_status": "unemployed",
            "existing_loans": 0
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["rejected", "manual_review"]


def test_missing_required_body_fields(client):
    resp = client.post("/workflow/submit", json={})
    assert resp.status_code == 422  # FastAPI/Pydantic validation error


def test_status_for_nonexistent_request(client):
    resp = client.get("/workflow/does-not-exist/status")
    assert resp.status_code == 404


def test_audit_for_nonexistent_request(client):
    resp = client.get("/workflow/does-not-exist/audit")
    assert resp.status_code == 404
