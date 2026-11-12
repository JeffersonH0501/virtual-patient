"""Admin activity and submitted surveys are administrator-only."""
from app.models.medical_interview import MedicalInterviewDB
from app.models.perception_survey import PerceptionSurveyDB
from app.models.doctor_grading import DoctorAssignmentDB
from app.models.user import UserDB, UserRole
from app.routers.users import router
from app.routers.tests.test_admin_interview_history import history_api


def test_admin_activity_interviews_and_submitted_survey(history_api):
    client, actor = history_api
    client.app.include_router(router)
    db = client.history_db
    student_id, doctor_id = client.fixture_user_ids[:2]
    student, doctor = db.get(UserDB, student_id), db.get(UserDB, doctor_id)
    interview = db.query(MedicalInterviewDB).filter_by(user_id=student.id).filter(MedicalInterviewDB.start_time.isnot(None)).first()
    db.add(DoctorAssignmentDB(interview_id=interview.id, doctor_id=doctor.id, assigned_by_id=actor.id))
    db.add(PerceptionSurveyDB(user_id=student.id, status='DRAFT', answers={}, comments={}))
    db.flush()
    activity = {row['user_id']: row for row in client.get('/users/admin/activity').json()}
    assert activity[student.id]['has_interviews'] and not activity[student.id]['has_submitted_survey']
    assert activity[doctor.id]['has_interviews']
    assert client.get(f'/users/admin/{student.id}/survey').status_code == 404
    record = db.get(PerceptionSurveyDB, student.id)
    record.status = 'SUBMITTED'
    db.flush()
    assert client.get(f'/users/admin/{student.id}/survey').status_code == 200
    rows = client.get(f'/users/admin/{doctor.id}/interviews')
    assert rows.status_code == 200
    assert any(row['id'] == interview.id and row['is_assigned'] for row in rows.json())
    actor.role = UserRole.DOCTOR
    assert client.get('/users/admin/activity').status_code == 403
    assert client.get(f'/users/admin/{student.id}/survey').status_code == 403
    assert client.get(f'/users/admin/{student.id}/interviews').status_code == 403
