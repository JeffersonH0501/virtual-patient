"""Self-assessment ownership, blinding and reuse of the human rating contract."""
from datetime import datetime, timezone
import pytest
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserDB, UserRole
from app.models.self_rating import SelfRatingDB
from app.routers.tests.test_teacher_grading import grading_api, history_api, payload


@pytest.fixture
def owner_api(grading_api):
    client, actor, db, interview_id, _ = grading_api
    interview = db.get(MedicalInterviewDB, interview_id)
    actor.id = interview.user_id
    actor.role = UserRole.STUDENT
    interview.start_time = datetime.now(timezone.utc)
    interview.end_time = datetime.now(timezone.utc)
    db.commit()
    return client, actor, db, interview


def test_owner_is_blinded_until_complete_self_submission(owner_api):
    client, actor, db, interview = owner_api
    base = f"/medical-interviews/{interview.id}"
    response = client.get(base + "/complete")
    assert response.status_code == 200
    assert response.json()["review_access"]["self_assessment_required"] is True
    assert "AUTOMATIC_SECRET" not in response.text
    assert client.get(base + "/teacher-ratings").status_code == 403
    assert client.get(base + "/reviewers").status_code == 403
    workspace = base + "/self-rating"
    assert client.get(workspace).json()["status"] == "pending"
    for _ in range(2):
        assert client.post(workspace + "/start").status_code == 200
    assert db.query(SelfRatingDB).filter_by(interview_id=interview.id).count() == 1
    assert client.put(workspace + "/draft", json={"results": payload()["results"][:1]}).status_code == 200
    assert client.get(base + "/complete").json()["review_access"]["can_view_assessments"] is False
    assert client.post(workspace + "/submit", json=payload(0)).status_code == 200
    result = client.get(base + "/complete").json()
    assert result["review_access"]["can_view_assessments"] is True
    assert result["review_access"]["self_assessment_required"] is False
    assert result["interview_evaluation"] is None
    assert result["multimodal_interview_evaluation"]["overall_score"] == 4.5
    assert client.get(workspace).json()["overall_score"] == 0


@pytest.mark.parametrize("invalid", ["partial", "empty_feedback", "duplicate", "out_of_range"])
def test_self_submission_preserves_six_category_validation(owner_api, invalid):
    client, _, _, interview = owner_api
    base = f"/medical-interviews/{interview.id}/self-rating"
    assert client.post(base + "/start").status_code == 200
    body = payload()
    if invalid == "partial":
        body["results"].pop()
    elif invalid == "empty_feedback":
        body["results"][0]["feedback"] = "  "
    elif invalid == "duplicate":
        body["results"][1]["aspect"] = body["results"][0]["aspect"]
    else:
        body["results"][0]["score"] = 6
    assert client.post(base + "/submit", json=body).status_code == 422
    assert client.get(base).json()["status"] == "in_progress"


def test_self_rating_is_owner_only_and_available_during_processing(owner_api):
    client, actor, db, interview = owner_api
    interview.status = "processing"
    db.commit()
    base = f"/medical-interviews/{interview.id}"
    assert client.get(base + "/recap").status_code == 200
    assert client.post(base + "/self-rating/start").status_code == 200
    owner_id = actor.id
    actor.id = db.query(UserDB).filter(UserDB.id != owner_id).first().id
    for suffix, method in [("", "get"), ("/start", "post"), ("/submit", "post")]:
        response = getattr(client, method)(base + "/self-rating" + suffix, **({"json": payload()} if suffix == "/submit" else {}))
        assert response.status_code == 404


def test_teacher_can_self_assess_own_interview_and_submission_updates_are_atomic(owner_api):
    client, actor, db, interview = owner_api
    actor.role = UserRole.TEACHER
    db.get(UserDB, actor.id).role = UserRole.TEACHER
    db.commit()
    base = f"/medical-interviews/{interview.id}/self-rating"
    assert client.post(base + "/start").status_code == 200
    assert client.post(base + "/submit", json=payload(3)).status_code == 200
    timestamp = db.get(SelfRatingDB, interview.id).submitted_at
    assert client.put(base + "/draft", json=payload(1)).status_code == 409
    assert client.post(base + "/submit", json=payload(4)).status_code == 200
    db.expire_all()
    assert db.get(SelfRatingDB, interview.id).submitted_at == timestamp
    assert db.get(SelfRatingDB, interview.id).overall_score == 4


def test_self_rating_is_deleted_with_its_interview(owner_api):
    client, _, db, interview = owner_api
    identifier = interview.id
    base = f"/medical-interviews/{identifier}/self-rating"
    assert client.post(base + "/start").status_code == 200
    assert client.post(base + "/submit", json=payload(3)).status_code == 200
    db.delete(interview)
    db.commit()
    db.expire_all()
    assert db.get(SelfRatingDB, identifier) is None

@pytest.mark.parametrize('status', ['processing', 'completed'])
def test_own_history_exposes_manual_submission_status(owner_api, status):
    client, _, db, interview = owner_api
    interview.status = status
    db.commit()
    def row():
        response = client.get('/medical-interviews')
        assert response.status_code == 200, response.text
        return next(item for item in response.json() if item['id'] == interview.id)
    assert row()['is_assigned'] is False
    assert row()['manual_rating_status'] == 'pending'
    path = f'/medical-interviews/{interview.id}/self-rating'
    assert client.post(path + '/start').status_code == 200
    assert row()['manual_rating_status'] == 'in_progress'
    assert client.post(path + '/submit', json=payload(3)).status_code == 200
    assert row()['manual_rating_status'] == 'submitted'
