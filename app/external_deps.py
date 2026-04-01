import hashlib
import random
import time
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Tweak this to test retry logic - 15% failure rate by default
_FAILURE_RATE = 0.15
_FORCE_FAIL = False  # Set True in tests to force failure every time


class ExternalDependencyError(Exception):
    """Raised when a downstream service is unavailable."""
    pass


def _stable_seed(applicant_name: str) -> int:
    digest = hashlib.sha256(applicant_name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def get_credit_score(applicant_name: str, force_fail: bool = False) -> Dict[str, Any]:
    """
    Simulated credit bureau API call.
    Introduces realistic latency and occasional failures to test retry logic.
    Score is deterministic based on applicant name so tests stay reproducible.
    """
    # Simulate network round-trip
    time.sleep(random.uniform(0.05, 0.3))

    if force_fail or _FORCE_FAIL or random.random() < _FAILURE_RATE:
        logger.warning("Credit bureau API timeout for: %s", applicant_name)
        raise ExternalDependencyError("Credit bureau: connection timed out (504)")

    seed = _stable_seed(applicant_name)
    base = (seed % 401) + 400  # 400-800 range

    return {
        "provider": "MockCreditBureau v2",
        "applicant_name": applicant_name,
        "credit_score": base,
        "credit_age_months": ((seed // 10) % 96) + 12,
        "active_accounts": (seed // 100 % 5),
        "defaults_last_2_years": 0 if base >= 600 else (seed // 1000 % 2),
        "retrieved_at": time.time(),
        "status": "success"
    }


def get_employment_verification(applicant_name: str, employer: str = None) -> Dict[str, Any]:
    """Simulated employment verification service."""
    time.sleep(random.uniform(0.02, 0.1))
    return {
        "provider": "MockEmpVerify",
        "verified": True,
        "employment_type": "full_time",
        "months_at_current_employer": (hash(applicant_name) % 48) + 6
    }
