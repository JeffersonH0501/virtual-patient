"""Owner eligibility, persistence and submission of perception surveys."""
from datetime import datetime, timezone
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




def prepare(state):
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = InterviewStatus.COMPLETED
        db.add(UserHypothesisDB(interview_id=state.id, hypothesis_order=1, hypothesis_text="Synthetic"))
        db.add(SelfRatingDB(interview_id=state.id, rubric_version="test", rubric_snapshot={}, results=[], submitted_at=datetime.now(timezone.utc)))
        db.add(InterviewEvaluationDB(medical_interview_id=state.id, evaluation_condition="TEXT_PLUS_MULTIMODAL", evaluation_results=[], overall_score=3))
        db.add(InterviewRecordingDB(medical_interview_id=state.id, status="ready", started_at=datetime.now(timezone.utc),
            consent_policy_version="synthetic", capture_config={"evaluation_processing": {"status": "complete"}}))
        db.commit()


@pytest.mark.parametrize('role', [UserRole.STUDENT, UserRole.DOCTOR])
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
    draft = {'answers': {'SUS-01': 5, 'EVA-01': 3}, 'comments': {'SUS': 'Draft'}, 'action': 'save'}
    assert state.client.put('/perception-survey', json=draft).json()['status'] == 'DRAFT'
    assert state.client.put('/perception-survey', json={**draft, 'action': 'submit'}).status_code == 422
    answers = {question: 3 for question in perception_survey.QUESTION_IDS}
    result = state.client.put('/perception-survey', json={'answers': answers, 'comments': {}, 'action': 'submit'})
    assert result.status_code == 200
    assert result.json()['sus_score'] == 50 and result.json()['questionnaire_version'] == perception_survey.QUESTIONNAIRE_VERSION
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
    for answers in ({'SUS-01': 6}, {'SUS-01': True}, {'OTHER': 1}):
        assert state.client.put('/perception-survey', json={'answers': answers, 'action': 'save'}).status_code == 422
    with Session(state.engine) as db:
        owner = db.get(UserDB, state.actor.id)
        other = UserDB(name='Other', email='other@example.org', hashed_password='unused', role=UserRole.STUDENT)
        db.add(other); db.commit(); other_id = other.id
    state.client.put('/perception-survey', json={'answers': {'SUS-01': 3}, 'action': 'save'})
    state.actor.id = other_id
    response = state.client.get('/perception-survey').json()
    assert response['eligible'] is False and response['answers'] == {}
    state.actor.role = UserRole.ADMIN
    assert state.client.get('/perception-survey').status_code == 403


def test_survey_requires_at_least_one_hypothesis(lifecycle_api):
    state = lifecycle_api
    state.client.app.include_router(perception_survey.router)
    state.actor.role = UserRole.STUDENT
    prepare(state)
    with Session(state.engine) as db:
        db.query(UserHypothesisDB).filter_by(interview_id=state.id).delete()
        db.commit()
    assert state.client.get('/perception-survey').json()['eligible'] is False
from types import SimpleNamespace
from app.routers.perception_survey import (
    COMMENT_KEYS, EVA_IDS, EXPERIENCE_DIMENSIONS, EXPERIENCE_IDS, QUESTION_IDS, QUESTIONNAIRE_VERSION, SUS_IDS, summarize, sus_score,
)
def test_questionnaire_blocks_and_item_codes_are_separate():
    assert SUS_IDS == [f'SUS-{i:02d}' for i in range(1, 11)]
    assert EXPERIENCE_IDS == ['VOZ-01', 'VOZ-02', 'VOZ-03', 'VOZ-04', 'CON-01', 'CON-02', 'CLI-01', 'CLI-02']
    assert EVA_IDS == [f'EVA-{i:02d}' for i in range(1, 13)]
    assert QUESTION_IDS == {*SUS_IDS, *EXPERIENCE_IDS, *EVA_IDS} and len(QUESTION_IDS) == 30
    assert not any(item.startswith(('CUQ', 'BUS', 'EXP')) for item in QUESTION_IDS)
    assert COMMENT_KEYS == {'SUS', 'EXP', 'EVA'}
@pytest.mark.parametrize('answers,expected', [
    ({item: 5 if index % 2 == 0 else 1 for index, item in enumerate(SUS_IDS)}, 100),
    ({item: 1 if index % 2 == 0 else 5 for index, item in enumerate(SUS_IDS)}, 0),
    ({item: 3 for item in SUS_IDS}, 50),
    ({item: 4 if index % 2 == 0 else 2 for index, item in enumerate(SUS_IDS)}, 75),
])
def test_sus_scoring_uses_odd_minus_one_and_even_five_minus(answers, expected):
    assert sus_score(answers) == expected
def test_sus_is_not_scored_while_items_are_missing_and_ignores_other_blocks():
    answers = {item: 5 for item in SUS_IDS[:9]}
    assert sus_score(answers) is None
    answers['SUS-10'] = 1
    complete = sus_score(answers)
    assert complete is not None
    assert sus_score({**answers, **{item: 1 for item in EXPERIENCE_IDS + EVA_IDS}}) == complete
def record(role, answers, version=QUESTIONNAIRE_VERSION, status='SUBMITTED'):
    return SimpleNamespace(role=role, answers=answers, questionnaire_version=version, status=status)
def test_summary_reports_blocks_separately_by_role_and_excludes_other_versions():
    neutral = {item: 3 for item in QUESTION_IDS}
    best = {**neutral, **{item: 5 if index % 2 == 0 else 1 for index, item in enumerate(SUS_IDS)}, 'VOZ-01': 5}
    summary = summarize([
        record(UserRole.STUDENT, neutral), record(UserRole.DOCTOR, best),
        record(UserRole.DOCTOR, neutral, version=None), record(UserRole.STUDENT, neutral, status='DRAFT'),
    ])
    assert summary['submitted_total'] == 3 and summary['excluded_other_versions'] == 1
    assert summary['all']['n'] == 2 and summary['all']['sus']['mean'] == 75
    assert summary['by_role']['student']['sus']['scores'] == [50] and summary['by_role']['doctor']['sus']['scores'] == [100]
    assert summary['all']['experience_items']['VOZ-01']['counts'] == {'1': 0, '2': 0, '3': 1, '4': 0, '5': 1}
    assert summary['by_role']['doctor']['experience_dimensions']['voice']['mean'] == 3.5
    assert set(summary['all']['eva_items']) == set(EVA_IDS) and 'SUS-01' not in summary['all']['eva_items']
def test_survey_summary_endpoint_is_admin_only(lifecycle_api):
    state = lifecycle_api
    state.client.app.include_router(perception_survey.router)
    assert state.client.get('/perception-survey/summary').status_code == 403
    state.actor.role = UserRole.ADMIN
    response = state.client.get('/perception-survey/summary')
    assert response.status_code == 200 and response.json()['questionnaire_version'] == QUESTIONNAIRE_VERSION
