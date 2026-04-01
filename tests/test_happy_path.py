"""
Happy path coverage with deterministic dependency data and AI review disabled.
"""


def test_root_page_renders_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Configurable Workflow Decision System" in resp.text


def test_api_info_lists_workflows(client):
    resp = client.get("/api-info")
    assert resp.status_code == 200
    assert resp.json()["available_workflows"] == ["employee_onboarding", "loan_approval"]


def test_loan_approval_returns_approved_decision(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    assert resp.status_code == 200
    data = resp.json()

    assert data["request_id"] == loan_request["request_id"]
    assert data["status"] == "approved"
    assert data["decision"] == "approved"
    assert "AI review is disabled" in data["ai_reasoning"]
    assert all(rule["passed"] is True for rule in data["rules_triggered"])


def test_response_has_complete_stage_history(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()

    stage_names = [stage["stage_name"] for stage in data["stage_history"]]
    assert stage_names == [
        "schema_validation",
        "credit_check",
        "rule_evaluation",
        "ai_decision",
        "final_decision",
    ]


def test_status_endpoint_returns_current_state(client, loan_request):
    client.post("/workflow/submit", json=loan_request)
    resp = client.get(f"/workflow/{loan_request['request_id']}/status")
    assert resp.status_code == 200

    data = resp.json()
    assert data["request_id"] == loan_request["request_id"]
    assert data["status"] == "approved"
    assert data["current_stage"] == "final_decision"


def test_audit_endpoint_includes_completion_event(client, loan_request):
    client.post("/workflow/submit", json=loan_request)
    resp = client.get(f"/workflow/{loan_request['request_id']}/audit")
    assert resp.status_code == 200

    data = resp.json()
    events = [entry["event"] for entry in data["audit_trail"]]
    assert data["final_status"] == "approved"
    assert events[0] == "workflow_started"
    assert events[-1] == "workflow_complete"


def test_employee_onboarding_workflow_returns_approved(client, onboarding_request):
    resp = client.post("/workflow/submit", json=onboarding_request)
    assert resp.status_code == 200

    data = resp.json()
    assert data["workflow_type"] == "employee_onboarding"
    assert data["status"] == "approved"
    assert data["decision"] == "approved"


def test_processing_time_recorded(client, loan_request):
    resp = client.post("/workflow/submit", json=loan_request)
    data = resp.json()
    assert data["processing_time_ms"] > 0


def test_list_workflows_endpoint(client):
    resp = client.get("/workflows")
    assert resp.status_code == 200
    assert resp.json() == {
        "workflows": ["employee_onboarding", "loan_approval"],
        "count": 2,
    }
