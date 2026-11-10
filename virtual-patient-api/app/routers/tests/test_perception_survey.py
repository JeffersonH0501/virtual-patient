"""Owner eligibility, persistence and submission of perception surveys."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import Session
from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB, InterviewStatus
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
from app.models.medical_interview.user_hypothesis import UserHypothesisDB
from app.models.self_rating import SelfRatingDB
from app.models.perception_survey import PerceptionSurveyDB
from app.models.user import UserDB, UserRole
from app.routers import perception_survey
from app.routers.tests.test_lifecycle_integrity import lifecycle_api


@pytest.mark.parametrize('answers,expected', [
    ({f'CUQ-{i:02d}': 5 if i % 2 else 1 for i in range(1, 17)}, 100),
    ({f'CUQ-{i:02d}': 1 if i % 2 else 5 for i in range(1, 17)}, 0),
    ({f'CUQ-{i:02d}': 3 for i in range(1, 17)}, 50),
])
def test_cuq_scoring_reverses_even_questions(answers, expected):
    record = SimpleNamespace(answers=answers, comments={}, status='DRAFT', created_at=None, submitted_at=None, updated_at=None)
    assert perception_survey.serialize(record, True)['cuq_score'] == expected


def prepare(state):
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = InterviewStatus.COMPLETED
        for number in range(1, 4):
            db.add(UserHypothesisDB(interview_id=state.id, hypothesis_order=number, hypothesis_text="Synthetic"))
        db.add(SelfRatingDB(interview_id=state.id, rubric_version="test", rubric_snapshot={}, results=[], submitted_at=datetime.now(timezone.utc)))
        db.add(InterviewEvaluationDB(medical_interview_id=state.id, evaluation_condition="TEXT_PLUS_MULTIMODAL", evaluation_results=[], overall_score=3))
        db.add(InterviewRecordingDB(medical_interview_id=state.id, status="ready", started_at=datetime.now(timezone.utc),
            consent_policy_version="synthetic", capture_config={"evaluation_processing": {"status": "complete"}}))
        db.commit()


@pytest.mark.parametrize('role', [UserRole.STUDENT, UserRole.TEACHER])
def test_survey_access_draft_submit_and_edit(lifecycle_api, role):
    state = lifecycle_api
    state.client.app.include_router(perception_survey.router)
    state.actor.role = role
    assert state.client.get('/perception-survey').json()['eligible'] is False
    assert state.client.put('/perception-survey', json={'answers': {}, 'action': 'save'}).status_code == 403
    prepare(state)
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {"evaluation_processing": {"status": "processing"}}
        db.commit()
    assert state.client.get('/perception-survey').json()['eligible'] is False
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {"evaluation_processing": {"status": "complete"}}
        db.commit()
    assert state.client.get('/perception-survey').json()['eligible'] is True
    draft = {'answers': {'CUQ-01': 5, 'EVA-01': 3}, 'comments': {'CUQ': 'Draft'}, 'action': 'save'}
    assert state.client.put('/perception-survey', json=draft).json()['status'] == 'DRAFT'
    assert state.client.put('/perception-survey', json={**draft, 'action': 'submit'}).status_code == 422
    answers = {question: (5 if question.startswith('CUQ-') and int(question[-2:]) % 2 else 1) for question in perception_survey.QUESTION_IDS}
    result = state.client.put('/perception-survey', json={'answers': answers, 'comments': {}, 'action': 'submit'})
    assert result.status_code == 200 and result.json()['cuq_score'] == 100
    submitted_at = result.json()['submitted_at']
    answers['EVA-01'] = 2
    result = state.client.put('/perception-survey', json={'answers': answers, 'comments': {'EVA': 'Updated'}, 'action': 'save'})
    assert result.json()['status'] == 'SUBMITTED' and result.json()['submitted_at'] == submitted_at
    with Session(state.engine) as db:
        assert db.query(PerceptionSurveyDB).count() == 1


def test_survey_rejects_invalid_answers_and_other_roles(lifecycle_api):
    state = lifecycle_api
    state.client.app.include_router(perception_survey.router)
    prepare(state)
    for answers in ({'CUQ-01': 6}, {'CUQ-01': True}, {'OTHER': 1}):
        assert state.client.put('/perception-survey', json={'answers': answers, 'action': 'save'}).status_code == 422
    with Session(state.engine) as db:
        owner = db.get(UserDB, state.actor.id)
        other = UserDB(name='Other', email='other@example.org', hashed_password='unused', role=UserRole.STUDENT, organization_id=owner.organization_id)
        db.add(other); db.commit(); other_id = other.id
    state.client.put('/perception-survey', json={'answers': {'CUQ-01': 3}, 'action': 'save'})
    state.actor.id = other_id
    response = state.client.get('/perception-survey').json()
    assert response['eligible'] is False and response['answers'] == {}
    state.actor.role = UserRole.SUPERUSER
    assert state.client.get('/perception-survey').status_code == 403
