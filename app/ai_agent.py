import os
import json
import logging
import google.generativeai as genai
from typing import Dict, Any, List
from app.models import RuleResult

logger = logging.getLogger(__name__)


def _build_model():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


def analyze_application(
    workflow_type: str,
    applicant_data: Dict[str, Any],
    rule_results: List[RuleResult],
    external_data: Dict[str, Any],
    preliminary_decision: str
) -> Dict[str, Any]:
    """
    Send application context to Gemini for an intelligent second-pass review.
    The model looks beyond hard rules - catches edge cases, unusual patterns,
    and explains the decision in plain language.
    """
    passed = [{"id": r.rule_id, "desc": r.description} for r in rule_results if r.passed]
    failed = [{"id": r.rule_id, "desc": r.description, "action": r.on_fail_action}
              for r in rule_results if not r.passed]

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

    try:
        model = _build_model()
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown code fences if Gemini wraps in them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        logger.info(
            "AI decision: %s | confidence: %s%%",
            result.get("final_decision"), result.get("confidence")
        )
        return result

    except json.JSONDecodeError as e:
        logger.error("AI response parse failed: %s | raw=%s", e, raw[:200])
        return _rule_based_fallback(preliminary_decision, rule_results)
    except Exception as e:
        logger.error("AI agent error: %s", e)
        return _rule_based_fallback(preliminary_decision, rule_results)


def _rule_based_fallback(preliminary_decision: str, rule_results: List[RuleResult]) -> Dict[str, Any]:
    """Used when Gemini is unavailable. Falls back to rule engine decision."""
    failed = [r for r in rule_results if not r.passed]
    passed_count = len([r for r in rule_results if r.passed])
    return {
        "final_decision": preliminary_decision,
        "confidence": 70,
        "reasoning": (
            f"Decision based on {len(rule_results)} rule checks: "
            f"{passed_count} passed, {len(failed)} failed. "
            f"AI analysis unavailable - rule engine decision applied."
        ),
        "key_factors": [r.description for r in rule_results[:3]],
        "risk_flags": [r.description for r in failed],
        "reviewer_note": "AI agent offline. Manual verification recommended."
    }
