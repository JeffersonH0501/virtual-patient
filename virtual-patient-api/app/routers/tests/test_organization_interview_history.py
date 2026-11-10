"""Organization history totals and interview-based counters on isolated fixtures."""
from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.auth import get_current_active_user
from app.models.organization import OrganizationDB
from app.models.clinical_case import ClinicalCaseDB
from app.models.user import User, UserDB, UserRole
from app.models.medical_interview import MedicalInterviewDB, InterviewStatus
from app.routers.medical_interviews import router


@pytest.fixture
def history_api():
    # Roll back every synthetic row; never change existing local application data.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            organizations = [OrganizationDB(name='History test ' + uuid4().hex, active=True) for _ in range(2)]
            db.add_all(organizations)
            db.flush()
            users = [UserDB(name='History fixture', email=uuid4().hex + '@example.org', hashed_password='unused', role=role, organization_id=organizations[org].id)
                     for role, org in [(UserRole.STUDENT, 0), (UserRole.TEACHER, 0), (UserRole.STUDENT, 1)]]
            db.add_all(users)
            case = ClinicalCaseDB(title='Synthetic history fixture', description='Test only')
            db.add(case)
            db.flush()
            now = datetime.now(timezone.utc)
            for owner, state, started in [
                (0, InterviewStatus.COMPLETED, True), (0, InterviewStatus.COMPLETED, True),
                (0, InterviewStatus.IN_PROGRESS, True), (0, InterviewStatus.IN_PROGRESS, True),
                (1, InterviewStatus.COMPLETED, True), (1, InterviewStatus.IN_PROGRESS, True),
                (0, InterviewStatus.INTERRUPTED, True), (0, InterviewStatus.PROCESSING, True),
                (2, InterviewStatus.COMPLETED, True), (0, InterviewStatus.IN_PROGRESS, False),
            ]:
                db.add(MedicalInterviewDB(user_id=users[owner].id, clinical_case_id=case.id, status=state, start_time=now if started else None))
            db.flush()
            db.commit()
            actor = User(id=users[1].id, name='Staff', email='staff@example.org', role=UserRole.SUPERUSER, organization_id=organizations[0].id)
            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_current_active_user] = lambda: actor
            with TestClient(app) as client:
                client.history_db = db
                yield client, actor, organizations[0].id, organizations[1].id
        transaction.rollback()


def test_superuser_counts_interviews_instead_of_distinct_students(history_api):
    client, _, organization, _ = history_api
    response = client.get(f'/medical-interviews/organization/{organization}/interview-counts')
    assert response.status_code == 200
    assert response.json() == {'active_interviews_count': 3, 'completed_interviews_count': 3}


def test_history_returns_exact_total_across_five_row_pages(history_api):
    client, _, organization, _ = history_api
    first = client.get(f'/medical-interviews/organization/{organization}?skip=0&limit=5')
    second = client.get(f'/medical-interviews/organization/{organization}?skip=5&limit=5')
    assert first.status_code == second.status_code == 200
    assert first.headers['X-Total-Count'] == second.headers['X-Total-Count'] == '8'
    assert len(first.json()) == 5 and len(second.json()) == 3
    assert not {row['id'] for row in first.json()}.intersection(row['id'] for row in second.json())
    assert all(row['public_id'] and row['start_time'] for row in first.json() + second.json())


def test_teacher_scope_excludes_teacher_interviews(history_api):
    client, actor, organization, _ = history_api
    actor.role = UserRole.TEACHER
    assert client.get(f'/medical-interviews/organization/{organization}/interview-counts').status_code == 403
    response = client.get(f'/medical-interviews/organization/{organization}?limit=5')
    assert response.status_code == 403


def test_history_and_counts_reject_students_and_other_organizations(history_api):
    client, actor, organization, other = history_api
    for suffix in ['', '/interview-counts']:
        assert client.get(f'/medical-interviews/organization/{other}{suffix}').status_code == 404
    actor.role = UserRole.STUDENT
    for suffix in ['', '/interview-counts']:
        assert client.get(f'/medical-interviews/organization/{organization}{suffix}').status_code == 403


@pytest.mark.parametrize('query', ['skip=-1', 'limit=0', 'limit=1001'])
def test_history_rejects_invalid_page_ranges(history_api, query):
    client, _, organization, _ = history_api
    assert client.get(f'/medical-interviews/organization/{organization}?{query}').status_code == 422


@pytest.mark.parametrize('owner_role', [UserRole.STUDENT, UserRole.TEACHER])
def test_superuser_deletes_organization_interviews_and_private_media(history_api, owner_role, tmp_path):
    client, _, organization, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).join(UserDB).filter(UserDB.organization_id == organization, UserDB.role == owner_role).first()
    interview_id = interview.id
    with patch('app.controllers.administrative_deletion.get_media_storage', return_value=SimpleNamespace(root=tmp_path)):
        response = client.delete(f'/medical-interviews/{interview_id}')
        assert response.status_code == 204
    assert db.get(MedicalInterviewDB, interview_id) is None
    history = client.get(f'/medical-interviews/organization/{organization}?limit=5')
    assert history.headers['X-Total-Count'] == '7'


@pytest.mark.parametrize('actor_role', [UserRole.STUDENT, UserRole.TEACHER])
def test_non_superusers_cannot_delete_other_people_interviews(history_api, actor_role):
    client, actor, organization, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.user_id != actor.id).join(UserDB).filter(UserDB.organization_id == organization).first()
    actor.role = actor_role
    with patch('app.routers.medical_interviews.get_media_storage') as storage:
        assert client.delete(f'/medical-interviews/{interview.id}').status_code == 404
        storage.assert_not_called()
    assert db.get(MedicalInterviewDB, interview.id) is not None


def test_superuser_cannot_delete_another_organization_or_provisioned_account_interview(history_api):
    client, actor, organization, other = history_api
    db = client.history_db
    other_interview = db.query(MedicalInterviewDB).join(UserDB).filter(UserDB.organization_id == other).first()
    protected = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.user_id == actor.id).first()
    db.get(UserDB, actor.id).role = UserRole.SUPERUSER
    db.flush()
    with patch('app.routers.medical_interviews.get_media_storage') as storage:
        for interview in [other_interview, protected]:
            assert client.delete(f'/medical-interviews/{interview.id}').status_code == 404
        storage.assert_not_called()


def test_owner_can_still_delete_own_interview(history_api, tmp_path):
    client, actor, _, _ = history_api
    db = client.history_db
    actor.role = UserRole.TEACHER
    interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.user_id == actor.id).first()
    with patch('app.controllers.administrative_deletion.get_media_storage', return_value=SimpleNamespace(root=tmp_path)):
        assert client.delete(f'/medical-interviews/{interview.id}').status_code == 204


def test_failed_private_media_deletion_retains_the_interview_for_retry(history_api):
    client, _, organization, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).join(UserDB).filter(UserDB.organization_id == organization, UserDB.role == UserRole.STUDENT).first()
    interview_id = interview.id
    with patch.object(db, 'commit', side_effect=RuntimeError('Synthetic commit failure')):
        assert client.delete(f'/medical-interviews/{interview_id}').status_code == 500
    assert db.get(MedicalInterviewDB, interview_id) is not None


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
def test_own_history_and_average_use_multimodal_score(history_api, role):
    from app.models.medical_interview.interview_evaluation import EvaluationCondition, InterviewEvaluationDB
    from app.routers import teacher_grading

    client, actor, _, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).filter_by(user_id=actor.id, status=InterviewStatus.COMPLETED).one()
    db.add_all([
        InterviewEvaluationDB(medical_interview_id=interview.id, evaluation_results=[],
                              overall_score=1.0, evaluation_condition=EvaluationCondition.TEXT_ONLY.value),
        InterviewEvaluationDB(medical_interview_id=interview.id, evaluation_results=[],
                              overall_score=4.0, evaluation_condition=EvaluationCondition.TEXT_PLUS_MULTIMODAL.value),
    ])
    db.flush()
    actor.role = role

    hidden = client.get("/medical-interviews").json()
    assert next(row for row in hidden if row["id"] == interview.id)["evaluation_score"] is None
    assert client.get("/medical-interviews/my/average-score").json()["average_score"] is None
    client.app.include_router(teacher_grading.router)
    path = f"/medical-interviews/{interview.id}/self-rating"
    assert client.post(path + "/start").status_code == 200
    assert client.post(path + "/submit", json={"results": [
        {"aspect": aspect, "score": 3, "feedback": "Synthetic independent rating"} for aspect in teacher_grading.ASPECTS
    ]}).status_code == 200

    response = client.get("/medical-interviews")
    assert response.status_code == 200
    assert next(row for row in response.json() if row["id"] == interview.id)["evaluation_score"] == 4.0
    assert client.get("/medical-interviews/my/average-score").json()["average_score"] == 4.0


def test_organization_history_uses_multimodal_score_and_not_text_score(history_api):
    from app.models.medical_interview.interview_evaluation import EvaluationCondition, InterviewEvaluationDB
    client, _, organization, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).join(UserDB).filter(
        UserDB.organization_id == organization, UserDB.role == UserRole.STUDENT,
        MedicalInterviewDB.status == InterviewStatus.COMPLETED).first()
    db.add_all([
        InterviewEvaluationDB(medical_interview_id=interview.id, evaluation_results=[], overall_score=1.0,
                              evaluation_condition=EvaluationCondition.TEXT_ONLY.value),
        InterviewEvaluationDB(medical_interview_id=interview.id, evaluation_results=[], overall_score=4.0,
                              evaluation_condition=EvaluationCondition.TEXT_PLUS_MULTIMODAL.value),
    ])
    db.flush()
    response = client.get(f"/medical-interviews/organization/{organization}?limit=100")
    assert response.status_code == 200
    assert next(row for row in response.json() if row["id"] == interview.id)["evaluation_score"] == 4.0


@pytest.mark.parametrize("query", ["skip=-1", "limit=0", "limit=101"])
def test_own_history_rejects_invalid_page_ranges(history_api, query):
    client, _, _, _ = history_api
    assert client.get(f"/medical-interviews?{query}").status_code == 422
