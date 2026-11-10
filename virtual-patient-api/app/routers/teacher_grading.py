"""Assignment-only, independently submitted human ratings."""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.core.review_access import can_replay, can_read_assessments, require_assessments
from app.controllers.personality_controller import PersonalityController
from app.models.user import User, UserDB, UserRole
from app.models.medical_interview import MedicalInterviewDB
from app.models.teacher_grading import TeacherAssignmentDB, TeacherRatingDB
from app.models.self_rating import SelfRatingDB
from app.agents.prompts.evaluation_aspects import HUMAN_RATING_RUBRIC_VERSION, get_all_aspects

router = APIRouter(tags=["teacher-grading"])
RUBRIC_VERSION = HUMAN_RATING_RUBRIC_VERSION
ASPECTS = tuple(get_all_aspects("en"))


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teacher_ids: list[int] = Field(min_length=1)


class AssignmentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teacher_ids: list[int]


class RatingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    aspect: str
    score: Optional[float] = Field(default=None, ge=0, le=5)
    feedback: str = ""


class RatingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[RatingItem]


class SubmittedRatingItem(RatingItem):
    feedback: str = Field(min_length=1)

    @field_validator("feedback", mode="before")
    @classmethod
    def trim_feedback(cls, value):
        return value.strip() if isinstance(value, str) else value


class SubmittedRatingRequest(RatingRequest):
    results: list[SubmittedRatingItem]


def staff_interview(db, interview_id, actor):
    interview = db.get(MedicalInterviewDB, interview_id)
    if not interview or not can_replay(db, interview, actor):
        raise HTTPException(404, "Interview not found")
    return interview


def require_admin(actor):
    if actor.role != UserRole.SUPERUSER:
        raise HTTPException(403, "Superuser access required")


def rating_for(db, assignment):
    return db.query(TeacherRatingDB).filter_by(assignment_id=assignment.id).first()


def assignment_data(db, item):
    teacher = db.get(UserDB, item.teacher_id)
    rating = rating_for(db, item)
    return {"id": item.id, "interview_id": item.interview_id, "teacher_id": item.teacher_id,
            "teacher_name": teacher.name if teacher else None, "teacher_email": teacher.email if teacher else None, "assigned_at": item.assigned_at,
            "status": "submitted" if rating and rating.submitted_at else "in_progress" if item.started_at else "pending"}


def own_assignment(db, assignment_id, actor):
    item = db.query(TeacherAssignmentDB).filter_by(id=assignment_id).with_for_update().first()
    if actor.role != UserRole.TEACHER or not item or item.teacher_id != actor.id:
        raise HTTPException(404, "Assignment not found")
    staff_interview(db, item.interview_id, actor)
    return item


@router.get("/medical-interviews/{interview_id}/teacher-assignments")
def list_assignments(interview_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_admin(actor)
    staff_interview(db, interview_id, actor)
    return [assignment_data(db, item) for item in db.query(TeacherAssignmentDB).filter_by(interview_id=interview_id).order_by(TeacherAssignmentDB.id).all()]


@router.post("/medical-interviews/{interview_id}/teacher-assignments", status_code=201)
def assign_teachers(interview_id: int, payload: AssignmentRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_admin(actor)
    interview = staff_interview(db, interview_id, actor)
    db.query(MedicalInterviewDB).filter_by(id=interview_id).with_for_update().one()
    if interview.status != "completed" or db.get(UserDB, interview.user_id).role != UserRole.STUDENT:
        raise HTTPException(409, "Only completed student interviews can be assigned")
    if len(set(payload.teacher_ids)) != len(payload.teacher_ids):
        raise HTTPException(422, "Duplicate teachers")
    for teacher_id in payload.teacher_ids:
        teacher = db.get(UserDB, teacher_id)
        if not teacher or teacher.role != UserRole.TEACHER or teacher.disabled or teacher.organization_id != actor.organization_id or teacher.id == interview.user_id:
            raise HTTPException(422, "Invalid teacher")
    try:
        for teacher_id in payload.teacher_ids:
            db.add(TeacherAssignmentDB(interview_id=interview_id, teacher_id=teacher_id, assigned_by_id=actor.id))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Teacher already assigned") from error
    return list_assignments(interview_id, db, actor)


@router.delete("/teacher-assignments/{assignment_id}", status_code=204)
def withdraw_assignment(assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_admin(actor)
    item = db.query(TeacherAssignmentDB).filter_by(id=assignment_id).with_for_update().first()
    if not item:
        raise HTTPException(404, "Assignment not found")
    staff_interview(db, item.interview_id, actor)
    if item.started_at:
        raise HTTPException(409, "An assignment already started cannot be withdrawn")
    db.delete(item)
    db.commit()


@router.get("/teacher-assignment-counts")
def assignment_counts(db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    if actor.role != UserRole.TEACHER:
        raise HTTPException(403, "Teacher access required")
    counts = {"pending": 0, "in_progress": 0, "submitted": 0}
    for item in db.query(TeacherAssignmentDB).join(MedicalInterviewDB, TeacherAssignmentDB.interview_id == MedicalInterviewDB.id).join(UserDB, MedicalInterviewDB.user_id == UserDB.id).filter(TeacherAssignmentDB.teacher_id == actor.id, UserDB.organization_id == actor.organization_id).all():
        counts[assignment_data(db, item)["status"]] += 1
    return counts


@router.get("/teacher-assignments")
def assigned_interviews(response: Response, offset: int = Query(0, ge=0), limit: int = Query(5, ge=1, le=100), db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    if actor.role != UserRole.TEACHER:
        raise HTTPException(403, "Teacher access required")
    query = db.query(TeacherAssignmentDB).join(MedicalInterviewDB, TeacherAssignmentDB.interview_id == MedicalInterviewDB.id).join(UserDB, MedicalInterviewDB.user_id == UserDB.id).filter(TeacherAssignmentDB.teacher_id == actor.id, UserDB.organization_id == actor.organization_id)
    response.headers["X-Total-Count"] = str(query.count())
    result = []
    assignments = query.order_by(TeacherAssignmentDB.id.desc()).offset(offset).limit(limit).all()
    interviews = [db.get(MedicalInterviewDB, item.interview_id) for item in assignments]
    from app.controllers.medical_interview_controller import MedicalInterviewController
    durations = MedicalInterviewController(db)._recorded_durations(interviews)
    for item, interview in zip(assignments, interviews):
        personality = interview.personality
        personality_data = {"name": personality.name, "name_translations": personality.name_translations} if personality else {}
        PersonalityController.translate_personality_name_in_dict(personality_data, actor.preferred_language)
        evaluation = interview.multimodal_interview_evaluation
        result.append({**assignment_data(db, item), "student_name": interview.user.name,
                       "case_title": interview.clinical_case.title, "created_at": interview.created_at,
                       "personality_name": personality_data.get("name"), "total_duration": durations.get(interview.id),
                       "overall_score": evaluation.overall_score if evaluation and can_read_assessments(db, interview, actor) else None})
    return result


@router.get("/teacher-assignments/{assignment_id}")
def read_workspace(assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    item = own_assignment(db, assignment_id, actor)
    rating = rating_for(db, item)
    snapshot = rating.rubric_snapshot if rating else {language: get_all_aspects(language) for language in ("en", "es")}
    return {**assignment_data(db, item), "rubric": snapshot.get(actor.preferred_language, snapshot["en"]),
            "results": rating.results if rating else [], "overall_score": rating.overall_score if rating else None}


@router.post("/teacher-assignments/{assignment_id}/start")
def start_rating(assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    item = own_assignment(db, assignment_id, actor)
    if not item.started_at:
        item.started_at = datetime.now(timezone.utc)
        db.add(TeacherRatingDB(assignment_id=item.id, rubric_version=RUBRIC_VERSION,
                              rubric_snapshot={language: get_all_aspects(language) for language in ("en", "es")}, results=[]))
        db.commit()
    return read_workspace(assignment_id, db, actor)


def save_rating(assignment_id, payload, db, actor, submit):
    item = own_assignment(db, assignment_id, actor)
    rating = rating_for(db, item)
    if rating is None:
        raise HTTPException(409, "Rating must be started before saving")
    apply_rating_results(rating, payload, submit)
    db.commit()
    return read_workspace(assignment_id, db, actor)


def apply_rating_results(rating, payload, submit):
    """Validate and apply the shared human rating submission contract."""
    if rating.submitted_at and not submit:
        raise HTTPException(409, "Completed ratings must be saved with all six scores")
    keys = [entry.aspect for entry in payload.results]
    if len(set(keys)) != len(keys) or any(key not in ASPECTS for key in keys):
        raise HTTPException(422, "Invalid rating categories")
    if submit and (set(keys) != set(ASPECTS) or any(entry.score is None for entry in payload.results)):
        raise HTTPException(422, "All six scores are required")
    now = datetime.now(timezone.utc)
    rating.results = [{**entry.model_dump(), "timestamp": now.isoformat()} for entry in payload.results]
    if submit:
        rating.overall_score = round(sum(entry.score for entry in payload.results) / len(ASPECTS), 1)
        if rating.submitted_at is None:
            rating.submitted_at = now


@router.put("/teacher-assignments/{assignment_id}/draft")
def draft_rating(assignment_id: int, payload: RatingRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    return save_rating(assignment_id, payload, db, actor, False)


@router.post("/teacher-assignments/{assignment_id}/submit")
def submit_rating(assignment_id: int, payload: SubmittedRatingRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    return save_rating(assignment_id, payload, db, actor, True)


@router.get("/medical-interviews/{interview_id}/teacher-ratings")
def submitted_ratings(interview_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    interview = staff_interview(db, interview_id, actor)
    require_assessments(db, interview, actor)
    rows = db.query(TeacherRatingDB, TeacherAssignmentDB).join(TeacherAssignmentDB, TeacherRatingDB.assignment_id == TeacherAssignmentDB.id).filter(TeacherAssignmentDB.interview_id == interview_id, TeacherRatingDB.submitted_at.isnot(None)).order_by(TeacherRatingDB.id).all()
    if actor.role != UserRole.SUPERUSER:
        rows = [(rating, item) for rating, item in rows if item.teacher_id == actor.id and interview.user_id != actor.id]
    return [{"id": rating.id, "teacher_name": db.get(UserDB, item.teacher_id).name,
             "results": rating.results, "overall_score": rating.overall_score, "submitted_at": rating.submitted_at} for rating, item in rows]


@router.put("/medical-interviews/{interview_id}/teacher-assignments")
def replace_assignments(interview_id: int, payload: AssignmentSelection, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    require_admin(actor)
    interview = staff_interview(db, interview_id, actor)
    db.query(MedicalInterviewDB).filter_by(id=interview_id).with_for_update().one()
    if interview.status != "completed" or db.get(UserDB, interview.user_id).role != UserRole.STUDENT:
        raise HTTPException(409, "Only completed student interviews can be assigned")
    requested = set(payload.teacher_ids)
    if len(requested) != len(payload.teacher_ids):
        raise HTTPException(422, "Duplicate teachers")
    existing = db.query(TeacherAssignmentDB).filter_by(interview_id=interview_id).order_by(TeacherAssignmentDB.id).with_for_update().all()
    current = {item.teacher_id for item in existing}
    removed = [item for item in existing if item.teacher_id not in requested]
    if any(item.started_at or rating_for(db, item) for item in removed):
        raise HTTPException(409, "Assignments with a rating draft cannot be removed")
    for teacher_id in requested - current:
        teacher = db.get(UserDB, teacher_id)
        if not teacher or teacher.role != UserRole.TEACHER or teacher.disabled or teacher.organization_id != actor.organization_id:
            raise HTTPException(422, "Invalid teacher")
    try:
        for item in removed:
            db.delete(item)
        for teacher_id in requested - current:
            db.add(TeacherAssignmentDB(interview_id=interview_id, teacher_id=teacher_id, assigned_by_id=actor.id))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Assignments changed; reload and retry") from error
    return list_assignments(interview_id, db, actor)


@router.get("/medical-interviews/{interview_id}/reviewers")
def interview_reviewers(interview_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    interview = staff_interview(db, interview_id, actor)
    require_assessments(db, interview, actor)
    result = []
    for item in db.query(TeacherAssignmentDB).filter_by(interview_id=interview_id).order_by(TeacherAssignmentDB.id).all():
        if actor.role != UserRole.SUPERUSER and (item.teacher_id != actor.id or interview.user_id == actor.id):
            continue
        rating = rating_for(db, item)
        result.append({"assignment_id": item.id, "teacher_id": item.teacher_id,
                       "teacher_name": db.get(UserDB, item.teacher_id).name,
                       "status": "submitted" if rating and rating.submitted_at else "in_progress" if item.started_at else "pending",
                       "rating_id": rating.id if rating and rating.submitted_at else None})
    return result


def self_interview(db, interview_id, actor):
    interview = db.query(MedicalInterviewDB).filter_by(id=interview_id).with_for_update().first()
    if not interview or interview.user_id != actor.id or actor.role not in (UserRole.STUDENT, UserRole.TEACHER):
        raise HTTPException(404, "Interview not found")
    if interview.status not in ("processing", "completed") or interview.start_time is None:
        raise HTTPException(409, "Finish the interview before self-assessment")
    return interview


@router.get("/medical-interviews/{interview_id}/self-rating")
def read_self_workspace(interview_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    self_interview(db, interview_id, actor)
    rating = db.get(SelfRatingDB, interview_id)
    snapshot = rating.rubric_snapshot if rating else {language: get_all_aspects(language) for language in ("en", "es")}
    return {"id": interview_id, "interview_id": interview_id,
            "status": "submitted" if rating and rating.submitted_at else "in_progress" if rating else "pending",
            "rubric": snapshot.get(actor.preferred_language, snapshot["en"]),
            "results": rating.results if rating else [], "overall_score": rating.overall_score if rating else None}


@router.post("/medical-interviews/{interview_id}/self-rating/start")
def start_self_rating(interview_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    self_interview(db, interview_id, actor)
    if db.get(SelfRatingDB, interview_id) is None:
        db.add(SelfRatingDB(interview_id=interview_id, rubric_version=RUBRIC_VERSION,
                            rubric_snapshot={language: get_all_aspects(language) for language in ("en", "es")}, results=[]))
        db.commit()
    return read_self_workspace(interview_id, db, actor)


def save_self_rating(interview_id, payload, db, actor, submit):
    self_interview(db, interview_id, actor)
    rating = db.get(SelfRatingDB, interview_id)
    if rating is None:
        raise HTTPException(409, "Self-assessment must be started before saving")
    apply_rating_results(rating, payload, submit)
    db.commit()
    return read_self_workspace(interview_id, db, actor)


@router.put("/medical-interviews/{interview_id}/self-rating/draft")
def draft_self_rating(interview_id: int, payload: RatingRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    return save_self_rating(interview_id, payload, db, actor, False)


@router.post("/medical-interviews/{interview_id}/self-rating/submit")
def submit_self_rating(interview_id: int, payload: SubmittedRatingRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_active_user)):
    return save_self_rating(interview_id, payload, db, actor, True)
