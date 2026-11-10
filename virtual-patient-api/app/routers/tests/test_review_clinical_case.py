"""Source case access for manual assessment without exposing automatic results."""
import pytest
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserDB, UserRole
from app.routers import clinical_cases
from app.routers.tests.test_teacher_grading import grading_api, history_api, assign


@pytest.mark.parametrize('status', ['processing', 'completed'])
def test_owner_reads_full_localized_case_before_self_submission(grading_api, status):
    client, actor, db, interview_id, _ = grading_api
    interview = db.get(MedicalInterviewDB, interview_id)
    interview.status = status
    case = interview.clinical_case
    case.active = True
    case.chief_complaint = 'Synthetic source complaint'
    case.chief_complaint_translations = {'es': 'Motivo sintético de consulta'}
    db.commit()
    actor.id = interview.user_id
    actor.role = UserRole.STUDENT
    actor.preferred_language = 'es'
    response = client.get(f'/medical-interviews/{interview_id}/clinical-case')
    assert response.status_code == 200, response.text
    assert response.json()['id'] == interview.clinical_case_id
    assert response.json()['chief_complaint'] == 'Motivo sintético de consulta'
    assert 'AUTOMATIC_SECRET' not in response.text
    assert client.get(f'/medical-interviews/{interview_id}/complete').json()['review_access']['can_view_assessments'] is False
    client.app.include_router(clinical_cases.router)
    catalog = client.get(f'/clinical-cases/{case.id}')
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()['chief_complaint'] is None


def test_case_review_requires_assignment_or_ownership_and_current_organization(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    actor.role = UserRole.TEACHER
    path = f'/medical-interviews/{interview_id}/clinical-case'
    assert client.get(path).status_code == 404
    assign(client, actor, interview_id)
    actor.role = UserRole.TEACHER
    assert client.get(path).status_code == 200
    teacher_id = actor.id
    actor.id = second_id
    assert client.get(path).status_code == 404
    actor.id = teacher_id
    db.get(UserDB, db.get(MedicalInterviewDB, interview_id).user_id).organization_id += 1
    db.commit()
    assert client.get(path).status_code == 404


@pytest.mark.parametrize('status', ['in_progress', 'interrupted'])
def test_full_case_is_not_exposed_during_capture_or_interruption(grading_api, status):
    client, actor, db, interview_id, _ = grading_api
    interview = db.get(MedicalInterviewDB, interview_id)
    interview.status = status
    db.commit()
    actor.id = interview.user_id
    actor.role = UserRole.STUDENT
    assert client.get(f'/medical-interviews/{interview_id}/clinical-case').status_code == 409
    assert client.get('/medical-interviews/0/clinical-case').status_code == 404
