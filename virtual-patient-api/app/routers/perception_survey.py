"""Participant-owned survey and server-side eligibility."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.user import User, UserDB, UserRole
from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB, InterviewStatus
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB, EvaluationCondition
from app.models.medical_interview.user_hypothesis import UserHypothesisDB
from app.models.self_rating import SelfRatingDB
from app.models.perception_survey import PerceptionSurveyDB

router = APIRouter(prefix="/perception-survey", tags=["perception-survey"])
QUESTION_IDS = {*(f"CUQ-{i:02d}" for i in range(1, 17)), *(f"EVA-{i:02d}" for i in range(1, 10))}


class SurveyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, StrictInt] = Field(default_factory=dict)
    comments: dict[str, str] = Field(default_factory=dict)
    action: Literal["save", "submit"]

    @field_validator("answers")
    @classmethod
    def valid_answers(cls, values):
        if not set(values) <= QUESTION_IDS or any(value < 1 or value > 5 for value in values.values()):
            raise ValueError("Invalid question or Likert response")
        return values

    @field_validator("comments")
    @classmethod
    def valid_comments(cls, values):
        if not set(values) <= {"CUQ", "EVA"} or any(len(value) > 10000 for value in values.values()):
            raise ValueError("Invalid survey comments")
        return values


def eligible(db: Session, user_id: int) -> bool:
    hypotheses = db.query(UserHypothesisDB.interview_id).group_by(UserHypothesisDB.interview_id).having(func.count(UserHypothesisDB.id) == 3).subquery()
    return db.query(MedicalInterviewDB.id).join(SelfRatingDB, SelfRatingDB.interview_id == MedicalInterviewDB.id).join(
        InterviewEvaluationDB, InterviewEvaluationDB.medical_interview_id == MedicalInterviewDB.id).join(
        InterviewRecordingDB, InterviewRecordingDB.medical_interview_id == MedicalInterviewDB.id).filter(
        MedicalInterviewDB.user_id == user_id, MedicalInterviewDB.status == InterviewStatus.COMPLETED,
        SelfRatingDB.submitted_at.isnot(None), InterviewEvaluationDB.evaluation_condition == EvaluationCondition.TEXT_PLUS_MULTIMODAL.value,
        InterviewEvaluationDB.overall_score.isnot(None), InterviewRecordingDB.capture_config["evaluation_processing"]["status"].as_string() == "complete",
        MedicalInterviewDB.id.in_(db.query(hypotheses.c.interview_id))).first() is not None


def serialize(record, enabled):
    answers = record.answers if record else {}
    score = sum((answers[f"CUQ-{i:02d}"] - 1 if i % 2 else 5 - answers[f"CUQ-{i:02d}"]) for i in range(1, 17)) * 100 / 64 if all(f"CUQ-{i:02d}" in answers for i in range(1, 17)) else None
    return {"eligible": enabled, "status": record.status if record else "DRAFT", "answers": answers,
            "comments": record.comments if record else {}, "cuq_score": score,
            "created_at": record.created_at if record else None, "submitted_at": record.submitted_at if record else None,
            "updated_at": record.updated_at if record else None}


def require_role(actor):
    if actor.role not in (UserRole.STUDENT, UserRole.TEACHER):
        raise HTTPException(403, "Survey is available to students and teachers")


@router.get("")
def get_survey(db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_role(actor)
    record = db.get(PerceptionSurveyDB, actor.id)
    return serialize(record, bool(record and record.status == "SUBMITTED") or eligible(db, actor.id))


@router.put("")
def save_survey(payload: SurveyUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_role(actor)
    db.query(UserDB).filter_by(id=actor.id).with_for_update().one()
    record = db.get(PerceptionSurveyDB, actor.id)
    if not (record and record.status == "SUBMITTED") and not eligible(db, actor.id):
        raise HTTPException(403, "A completed interview and evaluation are required")
    submitting = payload.action == "submit" or bool(record and record.status == "SUBMITTED")
    if submitting and set(payload.answers) != QUESTION_IDS:
        raise HTTPException(422, "All 25 questions are required")
    if record is None:
        record = PerceptionSurveyDB(user_id=actor.id, status="DRAFT", answers={}, comments={})
        db.add(record)
    record.answers, record.comments = payload.answers, payload.comments
    if submitting:
        record.status = "SUBMITTED"
        record.submitted_at = record.submitted_at or datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return serialize(record, True)
