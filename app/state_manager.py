import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from app.models import WorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflow_state.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS workflow_states (
            request_id      TEXT PRIMARY KEY,
            workflow_type   TEXT NOT NULL,
            applicant_name  TEXT NOT NULL,
            status          TEXT NOT NULL,
            current_stage   TEXT NOT NULL,
            data            TEXT NOT NULL,
            stage_history   TEXT DEFAULT '[]',
            audit_trail     TEXT DEFAULT '[]',
            attempt_count   INTEGER DEFAULT 1,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_cache (
            request_id  TEXT PRIMARY KEY,
            response    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    logger.info("DB initialized at: %s", DB_PATH)


def save_state(state: WorkflowState):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()

    stage_history_json = []
    for s in state.stage_history:
        if hasattr(s, "model_dump"):
            stage_history_json.append(s.model_dump(mode="json"))
        else:
            stage_history_json.append(s)

    c.execute("""
        INSERT OR REPLACE INTO workflow_states
        (request_id, workflow_type, applicant_name, status, current_stage,
         data, stage_history, audit_trail, attempt_count, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        state.request_id,
        state.workflow_type,
        state.applicant_name,
        state.status.value,
        state.current_stage,
        json.dumps(state.data),
        json.dumps(stage_history_json),
        json.dumps(state.audit_trail),
        state.attempt_count,
        state.created_at.isoformat(),
        now
    ))

    conn.commit()
    conn.close()


def get_state(request_id: str) -> Optional[WorkflowState]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM workflow_states WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    cols = ["request_id", "workflow_type", "applicant_name", "status",
            "current_stage", "data", "stage_history", "audit_trail",
            "attempt_count", "created_at", "updated_at"]
    d = dict(zip(cols, row))

    return WorkflowState(
        request_id=d["request_id"],
        workflow_type=d["workflow_type"],
        applicant_name=d["applicant_name"],
        status=WorkflowStatus(d["status"]),
        current_stage=d["current_stage"],
        data=json.loads(d["data"]),
        stage_history=json.loads(d["stage_history"]),
        audit_trail=json.loads(d["audit_trail"]),
        attempt_count=d["attempt_count"],
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"])
    )


def save_idempotency_response(request_id: str, response: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO idempotency_cache (request_id, response, created_at)
        VALUES (?, ?, ?)
    """, (request_id, json.dumps(response, default=str), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_idempotency_response(request_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT response FROM idempotency_cache WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None
