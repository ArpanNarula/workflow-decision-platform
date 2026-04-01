import importlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from app.models import RuleResult

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = True) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def is_ai_review_enabled(stage_config: Optional[Dict[str, Any]] = None) -> bool:
    if stage_config and stage_config.get("enabled") is False:
        return False
    return _env_flag("ENABLE_AI_REVIEW", default=True)


def _build_model(model_name: str) -> Tuple[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")

    try:
        genai_module = importlib.import_module("google.genai")
        return "google.genai", genai_module.Client(api_key=api_key)
    except ModuleNotFoundError:
        legacy_module = importlib.import_module("google.generativeai")
        legacy_module.configure(api_key=api_key)
        return "google.generativeai", legacy_module.GenerativeModel(model_name)


def _generate_text(client_kind: str, client: Any, model_name: str, prompt: str) -> str:
    if client_kind == "google.genai":
        response = client.models.generate_content(model=model_name, contents=prompt)
        return (response.text or "").strip()

    response = client.generate_content(prompt)
    return response.text.strip()


def analyze_application(
    workflow_type: str,
    applicant_data: Dict[str, Any],
    rule_results: List[RuleResult],
    external_data: Dict[str, Any],
    preliminary_decision: str,
    stage_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send application context to an optional AI reviewer.
    If AI review is disabled or unavailable, fall back to the rule-based decision.
    """
    if not is_ai_review_enabled(stage_config):
        return _rule_based_fallback(
            preliminary_decision,
            rule_results,
            reason="Decision based on configured rules. AI review is disabled.",
            reviewer_note="AI review disabled via config or environment.",
        )

    passed = [{"id": result.rule_id, "desc": result.description} for result in rule_results if result.passed]
    failed = [
        {"id": result.rule_id, "desc": result.description, "action": result.on_fail_action}
        for result in rule_results
        if not result.passed
    ]
    model_name = (stage_config or {}).get("model", "gemini-1.5-flash")

    prompt = f"""You are an AI decision agent for a {workflow_type.replace("_", " ")} system.

APPLICANT DATA:
{json.dumps(applicant_data, indent=2)}

EXTERNAL DATA (credit bureau, etc.):
{json.dumps(external_data, indent=2)}

RULES PASSED ({len(passed)}): {json.dumps(passed)}
RULES FAILED ({len(failed)}): {json.dumps(failed)}

PRELIMINARY RULE-BASED DECISION: {preliminary_decision}

Your job:
1. Look at the full picture - not just rules. Are there red flags or positive signals the rules missed?
2. You may confirm or override the preliminary decision if you have strong reason.
3. Write a clear 2-3 sentence explanation a non-technical person can understand.
4. Assign a confidence score 0-100.

Respond ONLY with this exact JSON (no markdown, no extra text):
{{
  "final_decision": "approved" | "rejected" | "manual_review",
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 sentence plain English explanation>",
  "key_factors": ["<factor1>", "<factor2>", "<factor3>"],
  "risk_flags": ["<flag1>"] or [],
  "reviewer_note": "<any note for a human reviewer, or empty string>"
}}"""

    raw = ""
    try:
        client_kind, client = _build_model(model_name)
        raw = _generate_text(client_kind, client, model_name, prompt)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        logger.info(
            "AI decision: %s | confidence: %s%%",
            result.get("final_decision"),
            result.get("confidence"),
        )
        return result
    except json.JSONDecodeError as exc:
        logger.error("AI response parse failed: %s | raw=%s", exc, raw[:200])
        return _rule_based_fallback(
            preliminary_decision,
            rule_results,
            reason="AI review returned an invalid payload. Rule-based decision kept.",
            reviewer_note="AI response parse failed.",
        )
    except Exception as exc:
        logger.error("AI agent error: %s", exc)
        return _rule_based_fallback(
            preliminary_decision,
            rule_results,
            reason="Decision based on configured rules. AI review is unavailable.",
            reviewer_note=f"AI review skipped: {exc}",
        )


def _rule_based_fallback(
    preliminary_decision: str,
    rule_results: List[RuleResult],
    reason: str,
    reviewer_note: str,
) -> Dict[str, Any]:
    """Used when AI review is disabled or unavailable."""
    failed = [result for result in rule_results if not result.passed]
    passed_count = len([result for result in rule_results if result.passed])
    return {
        "final_decision": preliminary_decision,
        "confidence": 70,
        "reasoning": (
            f"Decision based on {len(rule_results)} rule checks: "
            f"{passed_count} passed, {len(failed)} failed. "
            f"{reason}"
        ),
        "key_factors": [result.description for result in rule_results[:3]],
        "risk_flags": [result.description for result in failed],
        "reviewer_note": reviewer_note,
    }
