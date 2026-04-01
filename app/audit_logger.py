import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


def create_audit_entry(event: str, stage: str, details: Dict[str, Any], status: str = "info") -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "stage": stage,
        "status": status,
        "details": details
    }
    logger.info("AUDIT | %-30s | %-20s | %s", event, stage, status)
    return entry
