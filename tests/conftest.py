import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.state_manager import init_db


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def loan_request():
    return {
        "request_id": f"test-{uuid.uuid4()}",
        "workflow_type": "loan_approval",
        "applicant_name": "Rahul Sharma",
        "data": {
            "age": 30,
            "monthly_income": 80000,
            "loan_amount": 500000,
            "employment_status": "employed",
            "loan_purpose": "home renovation",
            "existing_loans": 0
        }
    }


@pytest.fixture
def rejected_loan_request():
    return {
        "request_id": f"test-reject-{uuid.uuid4()}",
        "workflow_type": "loan_approval",
        "applicant_name": "Underage Applicant",
        "data": {
            "age": 16,
            "monthly_income": 8000,
            "loan_amount": 1000000,
            "employment_status": "unemployed",
            "existing_loans": 6
        }
    }


@pytest.fixture
def onboarding_request():
    return {
        "request_id": f"test-onboard-{uuid.uuid4()}",
        "workflow_type": "employee_onboarding",
        "applicant_name": "Priya Verma",
        "data": {
            "age": 25,
            "role": "Software Engineer",
            "department": "Engineering",
            "experience_years": 3,
            "offered_salary": 70000
        }
    }
