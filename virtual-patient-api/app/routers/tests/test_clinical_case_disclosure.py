"""Keep interview answer keys private while preserving profiles and reviewer access."""
import pytest

from app.controllers.clinical_case_controller import ClinicalCaseController
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserRole
from app.routers.tests.test_organization_interview_history import history_api
from app.routers.tests.test_read_only_clinical_cases import catalog
from app.routers.tests.test_teacher_grading import grading_api, assign


SECRET = "SYNTHETIC_PRIVATE_CASE_DETAIL"
CLINICAL_FIELDS = (
    "physical_requirements", "socioeconomic_status", "patient_context", "chief_complaint",
    "present_illness", "personal_medical_history", "surgical_history", "family_history",
    "medications", "habits", "allergies", "concerns",
)


def seed_private_case(db, case):
    case.age = 65
    case.weight_in_kg = 70
    for field in CLINICAL_FIELDS:
        setattr(case, field, SECRET)
        setattr(case, f"{field}_translations", {"en": SECRET, "es": SECRET})
    db.commit()


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER, UserRole.SUPERUSER])
def test_catalog_detail_only_exposes_clinical_content_to_administrator(catalog, role):
    client, actor, cases = catalog
    db = client.history_db
    seed_private_case(db, cases[0])
    actor.role = role
    response = client.get(f"/clinical-cases/{cases[0].id}?language=en")
    assert response.status_code == 200, response.text
    assert response.json()["age"] == 65 and response.json()["weight_in_kg"] == 70
    assert (SECRET in response.text) is (role == UserRole.SUPERUSER)
    internal_case = ClinicalCaseController(db).get_clinical_case_in_language(cases[0].id, "en")
    assert internal_case.present_illness == SECRET


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
@pytest.mark.parametrize("state", ["in_progress", "processing", "interrupted", "completed"])
@pytest.mark.parametrize("suffix", ["", "/complete"])
def test_interview_case_is_redacted_until_completion(catalog, role, state, suffix):
    client, actor, cases = catalog
    db = client.history_db
    interview = db.query(MedicalInterviewDB).filter_by(user_id=actor.id).first()
    interview.clinical_case_id = cases[0].id
    interview.status = state
    seed_private_case(db, cases[0])
    actor.role = role
    response = client.get(f"/medical-interviews/{interview.id}{suffix}?language=en")
    assert response.status_code == 200, response.text
    assert response.json()["clinical_case"]["age"] == 65
    assert (SECRET in response.text) is (state == "completed")
    assert db.get(type(cases[0]), cases[0].id).present_illness == SECRET


@pytest.mark.parametrize("suffix", ["", "/complete"])
def test_calibration_draft_does_not_expose_case(catalog, suffix):
    client, actor, cases = catalog
    db = client.history_db
    interview = db.query(MedicalInterviewDB).filter_by(user_id=actor.id).first()
    interview.clinical_case_id = cases[0].id
    interview.start_time = None
    interview.status = "in_progress"
    seed_private_case(db, cases[0])
    actor.role = UserRole.TEACHER
    response = client.get(f"/medical-interviews/{interview.id}{suffix}?language=en")
    assert response.status_code == 200, response.text
    assert SECRET not in response.text


def test_administrator_can_read_full_case_for_active_interview(catalog):
    client, actor, cases = catalog
    db = client.history_db
    interview = db.query(MedicalInterviewDB).filter_by(user_id=actor.id).first()
    interview.clinical_case_id = cases[0].id
    interview.status = "in_progress"
    seed_private_case(db, cases[0])
    actor.role = UserRole.SUPERUSER
    response = client.get(f"/medical-interviews/{interview.id}/complete?language=en")
    assert response.status_code == 200, response.text
    assert SECRET in response.text


def test_assigned_reviewer_can_read_case_without_unlocking_assessments(grading_api):
    client, actor, db, interview_id, _ = grading_api
    interview = db.get(MedicalInterviewDB, interview_id)
    seed_private_case(db, interview.clinical_case)
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.TEACHER
    response = client.get(f"/medical-interviews/{interview_id}/complete?language=en")
    assert response.status_code == 200, response.text
    assert SECRET in response.text
    assert response.json()["review_access"] == {
        "can_view_assessments": False, "assignment_id": assignment_id,
    }
    assert response.json()["interview_evaluation"] is None


@pytest.mark.parametrize("role", [UserRole.SUPERUSER, UserRole.TEACHER])
def test_review_does_not_cross_organization_boundary(grading_api, role):
    client, actor, db, interview_id, _ = grading_api
    seed_private_case(db, db.get(MedicalInterviewDB, interview_id).clinical_case)
    actor.role = role
    actor.organization_id = None
    response = client.get(f"/medical-interviews/{interview_id}/complete?language=en")
    assert response.status_code == 403
    assert SECRET not in response.text
