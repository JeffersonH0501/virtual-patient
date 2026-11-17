"""Participant-owned survey and server-side eligibility."""
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
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
# Questionnaire structure. Blocks are reported separately and never combined:
#   SUS: System Usability Scale (standardized instrument, scored 0-100).
#   VOZ/CON/CLI: eight own items on the spoken interaction (descriptive only, no total score).
#   EVA: perception of the automatic evaluation and its feedback (descriptive only).
QUESTIONNAIRE_VERSION = "sus10_exp8_eva12_v1"
SUS_IDS = [f"SUS-{i:02d}" for i in range(1, 11)]
EXPERIENCE_DIMENSIONS = {
    "voice": [f"VOZ-{i:02d}" for i in range(1, 5)],
    "conversation": [f"CON-{i:02d}" for i in range(1, 3)],
    "clinical": [f"CLI-{i:02d}" for i in range(1, 3)],
}
EXPERIENCE_IDS = [item for items in EXPERIENCE_DIMENSIONS.values() for item in items]
EVA_IDS = [f"EVA-{i:02d}" for i in range(1, 13)]
QUESTION_IDS = {*SUS_IDS, *EXPERIENCE_IDS, *EVA_IDS}
COMMENT_KEYS = {"SUS", "EXP", "EVA"}
def sus_score(answers: dict) -> float | None:
    """SUS (Brooke, 1996): odd items contribute answer - 1, even items 5 - answer, sum * 2.5 (0-100).

    Returns None while any of the ten items is unanswered.
    """
    if not all(isinstance(answers.get(item), int) and 1 <= answers[item] <= 5 for item in SUS_IDS):
        return None
    total = sum(answers[item] - 1 if index % 2 == 0 else 5 - answers[item] for index, item in enumerate(SUS_IDS))
    return total * 2.5


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
        if not set(values) <= COMMENT_KEYS or any(len(value) > 10000 for value in values.values()):
            raise ValueError("Invalid survey comments")
        return values


def eligible(db: Session, user_id: int) -> bool:
    hypotheses = db.query(UserHypothesisDB.interview_id).group_by(UserHypothesisDB.interview_id).subquery()
    return db.query(MedicalInterviewDB.id).join(SelfRatingDB, SelfRatingDB.interview_id == MedicalInterviewDB.id).join(
        InterviewEvaluationDB, InterviewEvaluationDB.medical_interview_id == MedicalInterviewDB.id).join(
        InterviewRecordingDB, InterviewRecordingDB.medical_interview_id == MedicalInterviewDB.id).filter(
        MedicalInterviewDB.user_id == user_id, MedicalInterviewDB.status == InterviewStatus.COMPLETED,
        SelfRatingDB.submitted_at.isnot(None), InterviewEvaluationDB.evaluation_condition == EvaluationCondition.TEXT_PLUS_MULTIMODAL.value,
        InterviewEvaluationDB.overall_score.isnot(None), InterviewRecordingDB.capture_config["evaluation_processing"]["status"].as_string() == "complete",
        MedicalInterviewDB.id.in_(db.query(hypotheses.c.interview_id))).first() is not None


def serialize(record, enabled):
    answers = record.answers if record else {}
    return {"eligible": enabled, "status": record.status if record else "DRAFT", "answers": answers,
            "sus_score": sus_score(answers), "questionnaire_version": record.questionnaire_version if record else None,
            "comments": record.comments if record else {},
            "created_at": record.created_at if record else None, "submitted_at": record.submitted_at if record else None,
            "updated_at": record.updated_at if record else None}


def require_role(actor):
    if actor.role not in (UserRole.STUDENT, UserRole.DOCTOR):
        raise HTTPException(403, "Survey is available to students and doctors")


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
        raise HTTPException(422, f"All {len(QUESTION_IDS)} questions are required")
    if record is None:
        record = PerceptionSurveyDB(user_id=actor.id, status="DRAFT", answers={}, comments={}, questionnaire_version=QUESTIONNAIRE_VERSION)
        db.add(record)
    record.answers, record.comments = payload.answers, payload.comments
    record.questionnaire_version = QUESTIONNAIRE_VERSION
    if submitting:
        record.status = "SUBMITTED"
        record.submitted_at = record.submitted_at or datetime.now(timezone.utc)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return serialize(record, True)
def _describe(values: list[float]) -> dict:
    """Descriptive statistics only; no inferential claims."""
    if not values:
        return {"n": 0, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    sd = (sum((value - mean) ** 2 for value in ordered) / (count - 1)) ** 0.5 if count > 1 else None
    return {"n": count, "mean": round(mean, 2), "sd": None if sd is None else round(sd, 2), "median": median,
            "min": ordered[0], "max": ordered[-1]}
def _item_stats(rows: list[dict], items: list[str]) -> dict:
    stats = {}
    for item in items:
        values = [row[item] for row in rows if item in row]
        stats[item] = {**_describe(values), "counts": {str(level): values.count(level) for level in range(1, 6)}}
    return stats
def summarize(records) -> dict:
    """Blocks stay separate: SUS (0-100), the eight experience items and the EVA items.

    Only submitted surveys of the current questionnaire version are summarized. Older or unversioned
    submissions are counted but excluded, because their items are not comparable.
    """
    submitted = [record for record in records if record.status == "SUBMITTED"]
    current = [record for record in submitted if record.questionnaire_version == QUESTIONNAIRE_VERSION]
    def block(selected):
        rows = [record.answers for record in selected]
        scores = [score for score in (sus_score(row) for row in rows) if score is not None]
        dimensions = {}
        for name, items in EXPERIENCE_DIMENSIONS.items():
            per_person = [sum(row[item] for item in items) / len(items) for row in rows if all(item in row for item in items)]
            dimensions[name] = _describe(per_person)
        return {"n": len(selected), "sus": {**_describe(scores), "scores": sorted(scores),
                "bins": {f"{low}-{low + 19 if low < 80 else 100}": sum(low <= s < (low + 20 if low < 80 else 100.01) for s in scores)
                         for low in range(0, 100, 20)}},
                "experience_items": _item_stats(rows, EXPERIENCE_IDS), "experience_dimensions": dimensions,
                "eva_items": _item_stats(rows, EVA_IDS)}
    roles = {}
    for role in (UserRole.STUDENT, UserRole.DOCTOR):
        roles[role.value] = block([record for record in current if record.role == role])
    return {"questionnaire_version": QUESTIONNAIRE_VERSION, "submitted_total": len(submitted),
            "excluded_other_versions": len(submitted) - len(current), "all": block(current), "by_role": roles}
@router.get("/summary")
def survey_summary(db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    if actor.role != UserRole.ADMIN:
        raise HTTPException(403, "Administrators only")
    rows = db.query(PerceptionSurveyDB.status, PerceptionSurveyDB.questionnaire_version, PerceptionSurveyDB.answers, UserDB.role).join(
        UserDB, UserDB.id == PerceptionSurveyDB.user_id).all()
    return summarize([SimpleNamespace(status=status, questionnaire_version=version, answers=answers, role=role)
                      for status, version, answers, role in rows])
