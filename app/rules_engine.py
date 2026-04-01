import logging
from typing import Dict, Any, List, Tuple, Optional
from app.models import RuleResult

logger = logging.getLogger(__name__)


def _resolve_path(path: str, context: Dict[str, Any]) -> Any:
    """Resolve dotted path like 'data.age' or 'external.credit_score' from context dict."""
    parts = path.strip().split(".")
    val = context
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return None
    return val


def _parse_value(val_str: str, context: Dict[str, Any]) -> Any:
    """Try to resolve as context path first, then as a Python literal."""
    resolved = _resolve_path(val_str, context)
    if resolved is not None:
        return resolved
    try:
        return eval(val_str, {"__builtins__": {}})
    except Exception:
        return val_str


def evaluate_condition(condition: str, context: Dict[str, Any]) -> Tuple[bool, Any]:
    """
    Evaluate a single rule condition string.
    Supports: >=, <=, >, <, ==, !=, in (list)

    Examples:
        "data.age >= 18"
        "external.credit_score >= 600"
        "data.employment_status in ['employed', 'self_employed']"
        "data.loan_amount <= data.monthly_income * 10"
    """
    try:
        # Handle 'in' operator with list literal
        if " in [" in condition or " in [" in condition:
            left_str, right_str = condition.split(" in ", 1)
            left_val = _resolve_path(left_str.strip(), context)
            right_val = eval(right_str.strip(), {"__builtins__": {}})
            return (left_val in right_val), left_val

        # Handle arithmetic in right-hand side (e.g., data.monthly_income * 10)
        for op in [">=", "<=", "!=", ">", "<", "=="]:
            if f" {op} " in condition:
                left_str, right_str = condition.split(f" {op} ", 1)
                left_str = left_str.strip()
                right_str = right_str.strip()

                left_val = _resolve_path(left_str, context)

                # Right side may be arithmetic involving context paths
                # Replace context references in right_str with actual values
                for key in ["data", "external"]:
                    if key in right_str:
                        # Try resolving sub-paths
                        parts = right_str.split()
                        resolved_parts = []
                        for p in parts:
                            if p.startswith(f"{key}."):
                                rv = _resolve_path(p, context)
                                resolved_parts.append(str(rv) if rv is not None else "0")
                            else:
                                resolved_parts.append(p)
                        right_str = " ".join(resolved_parts)

                right_val = eval(right_str, {"__builtins__": {}})

                if left_val is None:
                    return False, None

                ops_map = {
                    ">=": lambda a, b: a >= b,
                    "<=": lambda a, b: a <= b,
                    ">": lambda a, b: a > b,
                    "<": lambda a, b: a < b,
                    "==": lambda a, b: a == b,
                    "!=": lambda a, b: a != b,
                }
                result = ops_map[op](left_val, right_val)
                return result, left_val

        logger.warning(f"Unparseable condition: {condition}")
        return False, None

    except Exception as e:
        logger.error(f"Rule eval error for '{condition}': {e}")
        return False, None


def evaluate_rules(rules_config: List[Dict], context: Dict[str, Any]) -> List[RuleResult]:
    """Run all rules in the config and collect results."""
    results = []
    for rule in rules_config:
        rule_id = rule.get("id", "unknown")
        description = rule.get("description", "")
        condition = rule.get("condition", "")
        on_fail = rule.get("on_fail", "reject")

        passed, value = evaluate_condition(condition, context)

        results.append(RuleResult(
            rule_id=rule_id,
            description=description,
            passed=passed,
            value_evaluated=value,
            on_fail_action=on_fail
        ))

        logger.info(f"  Rule [{rule_id}]: {'PASS' if passed else 'FAIL'} | value={value}")

    return results


def get_decision_from_rules(rule_results: List[RuleResult]) -> str:
    """
    Derive a decision from rule results.
    Priority order: reject > manual_review > approved
    """
    failed = [r for r in rule_results if not r.passed]

    if not failed:
        return "approved"

    if any(r.on_fail_action == "reject" for r in failed):
        return "rejected"

    if any(r.on_fail_action == "manual_review" for r in failed):
        return "manual_review"

    return "approved"
