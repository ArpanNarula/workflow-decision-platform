from app.rules_engine import evaluate_condition


def test_rules_engine_supports_arithmetic_and_membership():
    context = {
        "data": {
            "monthly_income": 80000,
            "loan_amount": 500000,
            "employment_status": "employed",
        },
        "external": {"credit_score": 720},
    }

    passed, value = evaluate_condition("data.loan_amount <= data.monthly_income * 10", context)
    assert passed is True
    assert value == 500000

    passed, value = evaluate_condition(
        "data.employment_status in ['employed', 'self_employed']",
        context,
    )
    assert passed is True
    assert value == "employed"


def test_rules_engine_rejects_unsafe_expressions():
    context = {"data": {}, "external": {}}
    passed, value = evaluate_condition("__import__('os').system('echo bad idea')", context)
    assert passed is False
    assert value is None
