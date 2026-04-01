import ast
import logging
import operator
from typing import Any, Dict, List, Tuple

from app.models import RuleResult

logger = logging.getLogger(__name__)

_ALLOWED_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_ALLOWED_COMPARE_OPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}


def _safe_eval(node: ast.AST, context: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, context)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return context.get(node.id)

    if isinstance(node, ast.Attribute):
        base = _safe_eval(node.value, context)
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr, None)

    if isinstance(node, ast.List):
        return [_safe_eval(element, context) for element in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval(element, context) for element in node.elts)

    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand, context)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        operator_fn = _ALLOWED_BIN_OPS.get(type(node.op))
        if operator_fn is None:
            raise ValueError(f"Unsupported arithmetic operator: {type(node.op).__name__}")
        return operator_fn(_safe_eval(node.left, context), _safe_eval(node.right, context))

    if isinstance(node, ast.BoolOp):
        values = [_safe_eval(value, context) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        left = _safe_eval(node.left, context)
        for operator_node, comparator_node in zip(node.ops, node.comparators):
            operator_fn = _ALLOWED_COMPARE_OPS.get(type(operator_node))
            if operator_fn is None:
                raise ValueError(
                    f"Unsupported comparison operator: {type(operator_node).__name__}"
                )
            right = _safe_eval(comparator_node, context)
            if not operator_fn(left, right):
                return False
            left = right
        return True

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def evaluate_condition(condition: str, context: Dict[str, Any]) -> Tuple[bool, Any]:
    """
    Evaluate a single rule condition string using a restricted AST parser.
    Supports comparisons, list membership, boolean operators, and basic arithmetic.
    """
    try:
        expression = ast.parse(condition, mode="eval")
        result = _safe_eval(expression, context)

        if isinstance(expression.body, ast.Compare):
            left_value = _safe_eval(expression.body.left, context)
        else:
            left_value = result

        return bool(result), left_value
    except Exception as exc:
        logger.error("Rule eval error for '%s': %s", condition, exc)
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
        results.append(
            RuleResult(
                rule_id=rule_id,
                description=description,
                passed=passed,
                value_evaluated=value,
                on_fail_action=on_fail,
            )
        )

        logger.info("  Rule [%s]: %s | value=%s", rule_id, "PASS" if passed else "FAIL", value)

    return results


def get_decision_from_rules(rule_results: List[RuleResult]) -> str:
    """
    Derive a decision from rule results.
    Priority order: reject > manual_review > approved
    """
    failed = [result for result in rule_results if not result.passed]

    if not failed:
        return "approved"

    if any(result.on_fail_action == "reject" for result in failed):
        return "rejected"

    if any(result.on_fail_action == "manual_review" for result in failed):
        return "manual_review"

    return "approved"
