"""One policy for interview access and pre-submission assessment blinding."""
from fastapi import HTTPException
from app.models.user import UserDB, UserRole
from app.models.clinical_case import ClinicalCaseSimplified
from app.models.teacher_grading import TeacherAssignmentDB, TeacherRatingDB
from app.models.self_rating import SelfRatingDB


def assignment_for(db, interview_id, user):
    return db.query(TeacherAssignmentDB).filter_by(interview_id=interview_id, teacher_id=user.id).first()


def can_replay(db, interview, user):
    if interview is None:
        return False
    if interview.user_id == user.id:
        return True
    owner = db.get(UserDB, interview.user_id)
    if not owner or user.organization_id is None or owner.organization_id != user.organization_id:
        return False
    if user.role == UserRole.SUPERUSER:
        return True
    return user.role == UserRole.TEACHER and assignment_for(db, interview.id, user) is not None


def can_read_assessments(db, interview, user):
    if not can_replay(db, interview, user):
        return False
    if user.role == UserRole.SUPERUSER:
        return True
    if interview.user_id == user.id:
        if interview.status == "in_progress":
            return True
        rating = db.get(SelfRatingDB, interview.id)
        return bool(rating and rating.submitted_at)
    assignment = assignment_for(db, interview.id, user)
    return bool(assignment and db.query(TeacherRatingDB).filter(
        TeacherRatingDB.assignment_id == assignment.id, TeacherRatingDB.submitted_at.isnot(None),
    ).first())


def require_assessments(db, interview, user):
    if not can_read_assessments(db, interview, user):
        raise HTTPException(403, "Submit your own rating before accessing assessments")


def redact_interview(db, interview, user, data):
    from app.controllers.interview_lifecycle import interview_lifecycle
    data["lifecycle"] = interview_lifecycle(interview, owner=interview.user_id == user.id)
    allowed = can_read_assessments(db, interview, user)
    assignment = assignment_for(db, interview.id, user) if user.role == UserRole.TEACHER else None
    data["review_access"] = {"can_view_assessments": allowed, "assignment_id": assignment.id if assignment else None,
                             "self_assessment_required": interview.user_id == user.id and user.role != UserRole.SUPERUSER and not allowed}
    if user.role == UserRole.SUPERUSER:
        owner = db.get(UserDB, interview.user_id)
        data["review_access"]["can_assign_teachers"] = bool(owner and owner.role == UserRole.STUDENT and interview.status == "completed")
    if user.role != UserRole.SUPERUSER:
        data["interview_evaluation"] = None
    if not allowed:
        for message in data.get("messages", []):
            message["message_metadata"] = {}
        data.update(interview_evaluation=None, multimodal_interview_evaluation=None,
                    session_notes=[], interview_metadata={})
        if interview.user_id == user.id:
            data["interview_metadata"] = {key: value for key, value in (interview.interview_metadata or {}).items()
                                          if key in ("calibration", "patient_response_language")}
    if user.role != UserRole.SUPERUSER and interview.status != "completed" and data.get("clinical_case"):
        data["clinical_case"] = ClinicalCaseSimplified.model_validate(data["clinical_case"]).model_dump()
    return data
