from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.database import get_db
from app.models import InterviewPerformanceEventDB, MedicalInterviewDB, User

router = APIRouter(prefix="/medical-interviews", tags=["interview-performance"])


class InterviewPerformanceEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    component: str
    operation: str
    phase: str
    status: str
    duration_ms: float | None
    trace_id: str | None
    metadata: dict[str, Any]


@router.get("/{interview_id}/performance-events", response_model=list[InterviewPerformanceEvent])
def list_interview_performance_events(
    interview_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[InterviewPerformanceEvent]:
    interview = db.get(MedicalInterviewDB, interview_id)
    if interview is None or (interview.interview_metadata or {}).get("calibration_test") is True:
        raise HTTPException(status_code=404, detail="Interview not found")
    rows = db.query(InterviewPerformanceEventDB).filter(
        InterviewPerformanceEventDB.medical_interview_id == interview_id,
    ).order_by(InterviewPerformanceEventDB.created_at, InterviewPerformanceEventDB.id).all()
    return [InterviewPerformanceEvent(
        id=row.id,
        created_at=row.created_at,
        component=row.component,
        operation=row.operation,
        phase=row.phase,
        status=row.status,
        duration_ms=row.duration_ms,
        trace_id=row.trace_id,
        metadata=row.metadata_json or {},
    ) for row in rows]
