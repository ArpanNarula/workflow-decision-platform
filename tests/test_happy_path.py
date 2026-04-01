"""
Happy path: valid input, all external deps succeed, expect a final decision.
"""


def test_loan_approval_returns_decision(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == loan_request["request_id"]
    assert data["status"] in ["approved", "manual_review", "rejected"]
    assert data["decision"] in ["approved", "manual_review", "rejected"]
    assert isinstance(data["ai_reasoning"], str) and len(data["ai_reasoning"]) > 0


def test_response_has_audit_trail(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()
    assert len(data["audit_trail"]) >= 2  # at minimum: started + completed


def test_response_has_rules_triggered(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()
    assert len(data["rules_triggered"]) > 0
    for rule in data["rules_triggered"]:
        assert "rule_id" in rule
        assert "passed" in rule


def test_response_has_stage_history(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()
    assert len(data["stage_history"]) >= 3  # validation + rules + ai at minimum


def test_status_endpoint(client, loan_request):
    client.post("/workflow/submit", json=loan_request)
    resp = client.get(f"/workflow/{loan_request['request_id']}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == loan_request["request_id"]
    assert data["status"] in ["approved", "manual_review", "rejected"]


def test_audit_endpoint(client, loan_request):
    client.post("/workflow/submit", json=loan_request)
    resp = client.get(f"/workflow/{loan_request['request_id']}/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["audit_trail"]) > 0


def test_employee_onboarding_workflow(client, onboarding_request):
    resp = client.post("/workflow/submit", json=onboarding_request)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_type"] == "employee_onboarding"
    assert data["status"] in ["approved", "manual_review", "rejected"]


def test_processing_time_recorded(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()
    assert data["processing_time_ms"] > 0


def test_list_workflows_endpoint(client):
    resp = client.get("/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert "loan_approval" in data["workflows"]
    assert "employee_onboarding" in data["workflows"]
