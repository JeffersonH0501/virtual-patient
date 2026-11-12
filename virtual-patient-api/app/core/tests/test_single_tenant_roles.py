"""Verify ownership, assignments, blinding and administrative access."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import engine
from app.core.review_access import can_read_assessments, can_replay
from app.models.clinical_case import ClinicalCaseDB
from app.models.medical_interview import InterviewStatus, MedicalInterviewDB
from app.models.self_rating import SelfRatingDB
from app.models.doctor_grading import DoctorAssignmentDB, DoctorRatingDB
from app.models.user import UserDB, UserRole
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.routers.medical_interviews import router
from app.routers.users import router as users_router
from app.core.captcha import require_captcha


def test_role_access_and_independent_blinding():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                users = [UserDB(name="Test", email=uuid4().hex + "@example.org", hashed_password="unused", role=role)
                         for role in (UserRole.STUDENT, UserRole.STUDENT, UserRole.DOCTOR, UserRole.DOCTOR, UserRole.ADMIN)]
                case = ClinicalCaseDB(title="Synthetic case", description="Test only")
                db.add_all([*users, case])
                db.flush()
                interview = MedicalInterviewDB(user_id=users[0].id, clinical_case_id=case.id, status=InterviewStatus.COMPLETED,
                                               start_time=datetime.now(timezone.utc))
                db.add(interview)
                db.flush()
                assignment = DoctorAssignmentDB(interview_id=interview.id, doctor_id=users[2].id, assigned_by_id=users[4].id)
                db.add(assignment)
                db.flush()
                assert [can_replay(db, interview, user) for user in users] == [True, False, True, False, True]
                assert [can_read_assessments(db, interview, user) for user in users] == [False, False, False, False, True]
                application = FastAPI()
                application.include_router(router)
                application.dependency_overrides[get_db] = lambda: db
                actor = {"user": users[4]}
                application.dependency_overrides[get_current_active_user] = lambda: actor["user"]
                with TestClient(application) as client:
                    assert client.get('/medical-interviews/admin/history').status_code == 200
                    actor["user"] = users[2]
                    assert client.get('/medical-interviews/admin/history').status_code == 403
                    actor["user"] = users[0]
                    assert client.get('/medical-interviews/admin/history').status_code == 403
                db.add(SelfRatingDB(interview_id=interview.id, rubric_version="test", rubric_snapshot={}, results=[], submitted_at=datetime.now(timezone.utc)))
                db.add(DoctorRatingDB(assignment_id=assignment.id, rubric_version="test", rubric_snapshot={}, results=[], submitted_at=datetime.now(timezone.utc)))
                db.flush()
                assert [can_read_assessments(db, interview, user) for user in users] == [True, False, True, False, True]
        finally:
            transaction.rollback()


def test_registration_and_admin_creation_without_organization():
    database = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    UserDB.__table__.create(database)
    with Session(database) as db:
        application = FastAPI()
        application.include_router(users_router)
        application.dependency_overrides[get_db] = lambda: db
        application.dependency_overrides[require_captcha] = lambda: None
        application.dependency_overrides[get_current_active_user] = lambda: UserDB(id=99, role=UserRole.ADMIN)
        with TestClient(application) as client:
            student = client.post('/users', json={'email': 'student@example.org', 'name': 'Student', 'password': 'secret',
                                                   'role': 'student', 'semester_range': 'first_four', 'university': 'University'})
            doctor = client.post('/users', json={'email': 'doctor@example.org', 'name': 'Doctor', 'password': 'secret', 'role': 'doctor'})
            forbidden = client.post('/users', json={'email': 'admin@example.org', 'name': 'Admin', 'password': 'secret', 'role': 'admin'})
            assert student.status_code == doctor.status_code == 201
            assert forbidden.status_code == 422
            response = client.get('/users/admin')
            assert response.status_code == 200
            assert {item['role'] for item in response.json()} == {'student', 'doctor'}
    database.dispose()
