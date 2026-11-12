from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import InterviewPerformanceEventDB, MedicalInterviewDB

_PRIVATE_FIELD_PARTS = ("transcript", "prompt", "answer", "content", "text", "token", "media")


def _safe_metadata(fields: dict[str, Any]) -> dict[str, Any]:
    def sanitize(value: Any, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str) and len(value) <= 160:
            return value
        if depth < 2 and isinstance(value, dict):
            return {
                str(key)[:80]: cleaned
                for key, item in list(value.items())[:40]
                if not any(part in str(key).lower() for part in _PRIVATE_FIELD_PARTS)
                if (cleaned := sanitize(item, depth + 1)) is not None
            }
        if depth < 2 and isinstance(value, (list, tuple)):
            return [cleaned for item in value[:40] if (cleaned := sanitize(item, depth + 1)) is not None]
        return None

    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if any(part in key.lower() for part in _PRIVATE_FIELD_PARTS):
            continue
        cleaned = sanitize(value)
        if cleaned is not None:
            safe[key[:80]] = cleaned
    return safe


def persist_interview_performance_event(
    interview_id: int | None,
    *,
    created_at: datetime | None = None,
    component: str,
    operation: str,
    phase: str,
    status: str,
    duration_ms: float | None = None,
    trace_id: str | None = None,
    fields: dict[str, Any] | None = None,
    db: Session | None = None,
) -> None:
    if interview_id is None:
        return
    owns_session = db is None
    session = db or SessionLocal()
    try:
        interview = session.get(MedicalInterviewDB, interview_id)
        if interview is None or (interview.interview_metadata or {}).get("calibration_test") is True:
            return
        session.add(InterviewPerformanceEventDB(
            medical_interview_id=interview_id,
            created_at=created_at,
            component=component[:80],
            operation=operation[:100],
            phase=phase[:40],
            status=status[:40],
            duration_ms=duration_ms,
            trace_id=trace_id[:100] if trace_id else None,
            metadata_json=_safe_metadata(fields or {}),
        ))
        if owns_session:
            session.commit()
    except Exception:
        if owns_session:
            session.rollback()
    finally:
        if owns_session:
            session.close()
