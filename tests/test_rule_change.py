"""
Rule change scenario: modify YAML config, hot-reload, verify new rules apply immediately.
No server restart needed - this is the key configurability proof.
"""
import uuid
import yaml
import os
import pytest
from app.config_loader import reload_workflow_config

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config", "workflows", "loan_approval.yaml"
)


def _read_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _write_config(config):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


@pytest.fixture(autouse=True)
def restore_config():
    """Always restore original config after each test - keeps test suite clean."""
    original = _read_config()
    yield
    _write_config(original)
    reload_workflow_config("loan_approval")


def test_tightening_income_rule_rejects_previously_valid(client):
    """
    Default min_income rule: monthly_income >= 25000.
    We raise it to 100000. A 60k/month applicant who was borderline now gets rejected.
    """
    config = _read_config()
    rule_stage = next(s for s in config["stages"] if s["type"] == "rules")
    income_rule = next(r for r in rule_stage["rules"] if r["id"] == "min_income")
    income_rule["condition"] = "data.monthly_income >= 100000"
    _write_config(config)
    reload_workflow_config("loan_approval")

    resp = client.post("/workflow/submit", json={
        "request_id": f"rule-change-{uuid.uuid4()}",
        "workflow_type": "loan_approval",
        "applicant_name": "Rule Change Test",
        "data": {
            "age": 28,
            "monthly_income": 60000,
            "loan_amount": 300000,
            "employment_status": "employed",
            "existing_loans": 0
        }
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"] == "rejected"
    income_rule_result = next(
        (r for r in data["rules_triggered"] if r["rule_id"] == "min_income"), None
    )
    assert income_rule_result is not None
    assert income_rule_result["passed"] is False


def test_adding_new_rule_gets_evaluated(client):
    """Add a brand new rule to the YAML. It should appear in rules_triggered."""
    config = _read_config()
    rule_stage = next(s for s in config["stages"] if s["type"] == "rules")
    rule_stage["rules"].append({
        "id": "max_loan_cap",
        "description": "Absolute loan cap: max Rs. 200,000",
        "condition": "data.loan_amount <= 200000",
        "on_fail": "reject"
    })
    _write_config(config)
    reload_workflow_config("loan_approval")

    resp = client.post("/workflow/submit", json={
        "request_id": f"new-rule-{uuid.uuid4()}",
        "workflow_type": "loan_approval",
        "applicant_name": "New Rule Test",
        "data": {
            "age": 30,
            "monthly_income": 80000,
            "loan_amount": 500000,
            "employment_status": "employed",
            "existing_loans": 0
        }
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"] == "rejected"
    new_rule = next((r for r in data["rules_triggered"] if r["rule_id"] == "max_loan_cap"), None)
    assert new_rule is not None
    assert new_rule["passed"] is False  # 500000 > 200000
