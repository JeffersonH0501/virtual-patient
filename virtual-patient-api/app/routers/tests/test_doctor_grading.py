"""Independent assignment, grading and assessment access integration tests."""
import pytest
from uuid import uuid4
from app.models.user import UserDB, UserRole
from app.models.medical_interview import MedicalInterviewDB, InterviewEvaluationDB, InterviewMessageDB, InterviewRecordingDB, InterviewTurnDB
from app.models.doctor_grading import DoctorAssignmentDB, DoctorRatingDB
from app.models.medical_interview.progress_summary import ProgressSummaryDB
from app.models.personality import PersonalityDB
from app.routers import doctor_grading, interview_recordings, summary, medical_interview_doctor_feedback, interview_messages, medical_interview_session_notes
from app.routers.tests.test_admin_interview_history import history_api


@pytest.fixture
def grading_api(history_api):
    client, actor = history_api
    actor.preferred_language = "en"
    for router in (doctor_grading.router, interview_recordings.router, summary.router, medical_interview_doctor_feedback.router, interview_messages.router, medical_interview_session_notes.router):
        client.app.include_router(router)
    client.app.dependency_overrides[interview_recordings._current_media_user] = lambda: actor
    db = client.history_db
    second = UserDB(name="Second doctor", email=uuid4().hex + "@example.org", hashed_password="unused", role=UserRole.DOCTOR)
    db.add(second)
    db.flush()
    interview = db.query(MedicalInterviewDB).join(UserDB).filter(MedicalInterviewDB.user_id.in_(client.fixture_user_ids), UserDB.role == UserRole.STUDENT, MedicalInterviewDB.status == "completed").first()
    for condition in ("TEXT_ONLY", "TEXT_PLUS_MULTIMODAL"):
        db.add(InterviewEvaluationDB(medical_interview_id=interview.id, evaluation_condition=condition,
                                    evaluation_results=[{"aspect": "show_interest", "score": 4.5, "feedback": "AUTOMATIC_SECRET", "timestamp": "2026-10-20T10:00:00"}], overall_score=4.5))
    db.add(InterviewMessageDB(interview_id=interview.id, content="Synthetic transcript", sender_type="user", message_metadata={"computed": "AUTOMATIC_SECRET"}))
    db.add(InterviewRecordingDB(medical_interview_id=interview.id, status="unavailable", started_at=interview.created_at, consent_policy_version="synthetic", capture_config={"observation_processing": {"status": "completed", "labels": "AUTOMATIC_SECRET"}}))
    db.add(InterviewTurnDB(medical_interview_id=interview.id, speaker="student", sequence=1, start_ms=0, end_ms=1000, transcript="Synthetic transcript", input_source="synthetic", timing_source="synthetic", timing_quality="measured", paraverbal={"label": "AUTOMATIC_SECRET"}, nonverbal_features={"label": "AUTOMATIC_SECRET"}))
    db.commit()
    yield client, actor, db, interview.id, second.id


def assign(client, actor, interview_id, doctor_id=None):
    actor.role = UserRole.ADMIN
    response = client.post(f"/medical-interviews/{interview_id}/doctor-assignments", json={"doctor_ids": [doctor_id or actor.id]})
    assert response.status_code == 201, response.text
    return next(item["id"] for item in response.json() if item["doctor_id"] == (doctor_id or actor.id))


def payload(score=0):
    return {"results": [{"aspect": aspect, "score": score, "feedback": "Independent rationale"} for aspect in doctor_grading.ASPECTS]}


@pytest.mark.parametrize("completed", [False, True])
def test_submission_requires_scores_but_not_comments_and_preserves_saved_ratings(grading_api, completed):
    client, actor, db, interview_id, _ = grading_api
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    base = f"/doctor-assignments/{assignment_id}"
    assert client.post(base + "/start").status_code == 200
    draft = {"results": [{"aspect": doctor_grading.ASPECTS[0], "score": 2}]}
    assert client.put(base + "/draft", json=draft).status_code == 200
    if completed:
        assert client.post(base + "/submit", json=payload(3)).status_code == 200
    previous = client.get(base).json()
    missing_score = payload(5)
    missing_score["results"][0]["score"] = None
    assert client.post(base + "/submit", json=missing_score).status_code == 422
    no_score_key = payload(5)
    del no_score_key["results"][0]["score"]
    assert client.post(base + "/submit", json=no_score_key).status_code == 422
    current = client.get(base).json()
    assert current["results"] == previous["results"]
    assert current["overall_score"] == previous["overall_score"]
    assert current["status"] == previous["status"]
    optional = payload(4)
    optional["results"][0]["feedback"] = "   "
    del optional["results"][1]["feedback"]
    optional["results"][2]["feedback"] = "  Updated rationale  "
    response = client.post(base + "/submit", json=optional)
    assert response.status_code == 200, response.text
    saved = response.json()["results"]
    assert [saved[0]["feedback"], saved[1]["feedback"], saved[2]["feedback"]] == ["", "", "Updated rationale"]
    assert response.json()["overall_score"] == 4


def test_assignment_listing_includes_case_details_duration_and_only_own_submitted_score(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    personality = PersonalityDB(name="Friendly patient", namespace_key=uuid4().hex,
                                name_translations={"es": "Paciente amable"})
    db.add(personality)
    db.flush()
    interview = db.get(MedicalInterviewDB, interview_id)
    interview.personality_id = personality.id
    interview.total_duration = 120
    db.commit()
    assignment_id = assign(client, actor, interview_id)
    second_assignment_id = assign(client, actor, interview_id, second_id)
    first_doctor_id = actor.id
    actor.role = UserRole.DOCTOR
    actor.id = second_id
    second_base = f"/doctor-assignments/{second_assignment_id}"
    assert client.post(second_base + "/start").status_code == 200
    assert client.post(second_base + "/submit", json=payload(5)).status_code == 200
    actor.id = first_doctor_id
    actor.preferred_language = "es"
    response = client.get("/doctor-assignments")
    assert response.status_code == 200, response.text
    row = next(item for item in response.json() if item["id"] == assignment_id)
    assert row["total_duration"] == 1
    assert row["personality_name"] == "Paciente amable"
    assert row["case_title"] == interview.clinical_case.title
    assert row["owner_name"] == interview.user.name
    assert "student_name" not in row
    assert row["overall_score"] is None
    base = f"/doctor-assignments/{assignment_id}"
    assert client.post(base + "/start").status_code == 200
    assert client.put(base + "/draft", json=payload(3)).status_code == 200
    row = next(item for item in client.get("/doctor-assignments").json() if item["id"] == assignment_id)
    assert row["status"] == "in_progress"
    assert row["overall_score"] is None
    assert client.post(base + "/submit", json=payload(0)).status_code == 200
    row = next(item for item in client.get("/doctor-assignments").json() if item["id"] == assignment_id)
    assert row["status"] == "submitted"
    assert row["overall_score"] == 4.5


def test_assignment_is_required_and_blinding_is_enforced_in_api(grading_api):
    client, actor, db, interview_id, _ = grading_api
    db.add(ProgressSummaryDB(medical_interview_id=interview_id, summary_text="Synthetic clinical summary"))
    db.commit()
    actor.role = UserRole.DOCTOR
    assert client.get(f"/medical-interviews/{interview_id}/complete").status_code == 403
    assignment_id = assign(client, actor, interview_id)
    shared_summary = client.get(f"/medical-interviews/{interview_id}/complete").json()["progress_summary"]
    assert shared_summary["summary_text"] == "Synthetic clinical summary"
    actor.role = UserRole.DOCTOR
    response = client.get(f"/medical-interviews/{interview_id}/complete")
    assert response.status_code == 200, response.text
    assert "AUTOMATIC_SECRET" not in response.text
    assert response.json()["interview_evaluation"] is None
    assert response.json()["progress_summary"] == shared_summary
    assert response.json()["review_access"] == {"can_view_assessments": False, "assignment_id": assignment_id, "self_assessment_required": False}
    for suffix in ("recap", "messages"):
        raw = client.get(f"/medical-interviews/{interview_id}/{suffix}")
        assert raw.status_code == 200, raw.text
        assert "AUTOMATIC_SECRET" not in raw.text
    for suffix in ("doctor-ratings", "evaluation/runs", "learning-moments", "summary", "doctor-feedback", "session-notes"):
        assert client.get(f"/medical-interviews/{interview_id}/{suffix}").status_code == 403, suffix
    assert client.get("/medical-interviews/admin/history").status_code == 403


def test_begin_save_reload_complete_zero_and_edit(grading_api):
    client, actor, db, interview_id, _ = grading_api
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    base = f"/doctor-assignments/{assignment_id}"
    assert client.get(base).json()["status"] == "pending"
    assert client.post(base + "/start").json()["status"] == "in_progress"
    assert client.post(base + "/start").status_code == 200
    assert db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).count() == 1
    assert client.put(base + "/draft", json={"results": payload()["results"][:1]}).status_code == 200
    assert len(client.get(base).json()["results"]) == 1
    assert client.post(base + "/submit", json={"results": []}).status_code == 422
    result = client.post(base + "/submit", json=payload())
    assert result.status_code == 200, result.text
    assert result.json()["overall_score"] == 0
    assert result.json()["status"] == "submitted"
    assert client.put(base + "/draft", json=payload(5)).status_code == 409
    first_completion = db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).one().submitted_at
    assert client.post(base + "/submit", json={"results": payload()["results"][:1]}).status_code == 422
    updated = client.post(base + "/submit", json=payload(5))
    assert updated.status_code == 200, updated.text
    assert updated.json()["overall_score"] == 5
    assert updated.json()["status"] == "submitted"
    assert db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).one().submitted_at == first_completion
    assert db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).count() == 1
    assert client.get(base).json()["results"][0]["score"] == 5
    assert "AUTOMATIC_SECRET" in client.get(f"/medical-interviews/{interview_id}/complete").text
    assert len(client.get(f"/medical-interviews/{interview_id}/doctor-ratings").json()) == 1
    assert client.get(f"/medical-interviews/{interview_id}/doctor-ratings").json()[0]["overall_score"] == 5
    listed = next(item for item in client.get("/doctor-assignments").json() if item["id"] == assignment_id)
    assert listed["overall_score"] == 4.5
    assert listed["status"] == "submitted"


def test_only_the_author_can_update_a_completed_rating(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    base = f"/doctor-assignments/{assignment_id}"
    assert client.post(base + "/start").status_code == 200
    assert client.post(base + "/submit", json=payload(3)).status_code == 200
    author_id = actor.id
    for user_id, role in ((second_id, UserRole.DOCTOR),
                          (db.get(MedicalInterviewDB, interview_id).user_id, UserRole.STUDENT),
                          (author_id, UserRole.ADMIN)):
        actor.id, actor.role = user_id, role
        assert client.post(base + "/submit", json=payload(5)).status_code == 404
    assert db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).one().overall_score == 3


def test_multiple_doctors_unlock_only_their_own_submission(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    first_id = actor.id
    first = assign(client, actor, interview_id)
    second = assign(client, actor, interview_id, second_id)
    actor.role = UserRole.DOCTOR
    client.post(f"/doctor-assignments/{first}/start")
    client.post(f"/doctor-assignments/{first}/submit", json=payload(4))
    actor.id = second_id
    assert client.get(f"/medical-interviews/{interview_id}/doctor-ratings").status_code == 403
    assert client.get(f"/doctor-assignments/{first}").status_code == 404
    client.post(f"/doctor-assignments/{second}/start")
    client.post(f"/doctor-assignments/{second}/submit", json=payload(3))
    assert len(client.get(f"/medical-interviews/{interview_id}/doctor-ratings").json()) == 1
    actor.id = db.get(MedicalInterviewDB, interview_id).user_id
    actor.role = UserRole.STUDENT
    assert client.get(f"/medical-interviews/{interview_id}/doctor-ratings").status_code == 403


def test_only_pending_assignments_can_be_withdrawn(grading_api):
    client, actor, db, interview_id, _ = grading_api
    assignment_id = assign(client, actor, interview_id)
    assert client.delete(f"/doctor-assignments/{assignment_id}").status_code == 204
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    client.post(f"/doctor-assignments/{assignment_id}/start")
    actor.role = UserRole.ADMIN
    assert client.delete(f"/doctor-assignments/{assignment_id}").status_code == 409


@pytest.mark.parametrize("score", [-1, 5.1, "NaN", "Infinity"])
def test_invalid_scores_are_rejected(grading_api, score):
    client, actor, db, interview_id, _ = grading_api
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    client.post(f"/doctor-assignments/{assignment_id}/start")
    assert client.post(f"/doctor-assignments/{assignment_id}/submit", json=payload(score)).status_code == 422


def test_assignment_duplicates_scope_and_roles(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    assignment_id = assign(client, actor, interview_id)
    assert client.post(f"/medical-interviews/{interview_id}/doctor-assignments", json={"doctor_ids": [actor.id]}).status_code == 409
    assert client.post(f"/medical-interviews/{interview_id}/doctor-assignments", json={"doctor_ids": [second_id, second_id]}).status_code == 422
    owner = db.get(MedicalInterviewDB, interview_id).user_id
    assert client.post(f"/medical-interviews/{interview_id}/doctor-assignments", json={"doctor_ids": [owner]}).status_code == 422
    # A doctor-owned completed interview can be assigned to another doctor.
    own_practice = db.query(MedicalInterviewDB).filter_by(user_id=actor.id, status="completed").first()
    assert client.post(f"/medical-interviews/{own_practice.id}/doctor-assignments", json={"doctor_ids": [second_id]}).status_code == 201
    actor.id = second_id
    actor.role = UserRole.DOCTOR
    assert client.get(f"/medical-interviews/{interview_id}/complete").status_code == 403
    assert client.post(f"/doctor-assignments/{assignment_id}/start").status_code == 404


@pytest.mark.parametrize("variant", ["duplicate", "unknown", "missing", "null"])
def test_submission_requires_exact_canonical_categories(grading_api, variant):
    client, actor, _, interview_id, _ = grading_api
    assignment_id = assign(client, actor, interview_id)
    actor.role = UserRole.DOCTOR
    client.post(f"/doctor-assignments/{assignment_id}/start")
    body = payload()
    if variant == "duplicate":
        body["results"][-1] = body["results"][0]
    elif variant == "unknown":
        body["results"][-1]["aspect"] = "unknown_category"
    elif variant == "missing":
        body["results"].pop()
    else:
        body["results"][-1]["score"] = None
    assert client.post(f"/doctor-assignments/{assignment_id}/submit", json=body).status_code == 422


def test_concurrent_saves_serialize_without_duplicate_or_mixed_ratings():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.core.database import engine
    from app.models.clinical_case import ClinicalCaseDB
    from app.models.user import User
    from datetime import datetime, timezone
    identifiers = None
    with Session(engine) as setup:
        people = [UserDB(name="Synthetic concurrency", email=uuid4().hex + "@example.org", hashed_password="unused", role=role) for role in (UserRole.ADMIN, UserRole.STUDENT, UserRole.DOCTOR)]
        setup.add_all(people)
        case = ClinicalCaseDB(title="Synthetic concurrency", description="Test only")
        setup.add(case); setup.flush()
        interview = MedicalInterviewDB(user_id=people[1].id, clinical_case_id=case.id, status="completed")
        setup.add(interview); setup.flush()
        assignment = DoctorAssignmentDB(interview_id=interview.id, doctor_id=people[2].id, assigned_by_id=people[0].id, started_at=datetime.now(timezone.utc))
        setup.add(assignment); setup.flush()
        setup.add(DoctorRatingDB(assignment_id=assignment.id, rubric_version="synthetic", rubric_snapshot={"en": doctor_grading.get_all_aspects("en")}, results=[]))
        setup.commit()
        identifiers = ([person.id for person in people], case.id, interview.id, assignment.id)
    user_ids, case_id, interview_id, assignment_id = identifiers
    gate = Barrier(2)
    def submit(score):
        actor = User(id=user_ids[2], name="Synthetic", email="synthetic@example.org", role=UserRole.DOCTOR)
        with Session(engine) as db:
            gate.wait(timeout=10)
            try:
                doctor_grading.save_rating(assignment_id, doctor_grading.RatingRequest(**payload(score)), db, actor, True)
                return 200
            except HTTPException as failure:
                return failure.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(submit, [3.5, 4.5])) == [200, 200]
        with Session(engine) as db:
            final = db.query(DoctorRatingDB).filter_by(assignment_id=assignment_id).one()
            assert final.overall_score in (3.5, 4.5)
            assert final.submitted_at is not None
            assert len(final.results) == 6
            assert all(item["score"] == final.overall_score for item in final.results)
    finally:
        with Session(engine) as cleanup:
            cleanup.delete(cleanup.get(MedicalInterviewDB, interview_id)); cleanup.flush()
            cleanup.delete(cleanup.get(ClinicalCaseDB, case_id))
            for user_id in user_ids:
                cleanup.delete(cleanup.get(UserDB, user_id))
            cleanup.flush()
            cleanup.commit()


def test_assignment_capability_excludes_admin_owned_and_unfinished_reviews(grading_api):
    client, actor, db, interview_id, _ = grading_api
    db.get(UserDB, actor.id).role = UserRole.ADMIN
    db.commit()
    assert client.get(f"/medical-interviews/{interview_id}/complete").json()["review_access"]["can_assign_doctors"] is True
    practice = db.query(MedicalInterviewDB).filter_by(user_id=actor.id, status="completed").first()
    assert client.get(f"/medical-interviews/{practice.id}/complete").json()["review_access"]["can_assign_doctors"] is False


def test_doctor_owned_interviews_can_be_assigned_to_another_doctor(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    owner_id = db.get(MedicalInterviewDB, interview_id).user_id
    db.get(UserDB, owner_id).role = UserRole.DOCTOR
    db.get(UserDB, actor.id).role = UserRole.ADMIN
    db.commit()
    admin_id = actor.id
    complete = f"/medical-interviews/{interview_id}/complete"
    assert client.get(complete).json()["review_access"]["can_assign_doctors"] is True
    path = f"/medical-interviews/{interview_id}/doctor-assignments"
    assert client.post(path, json={"doctor_ids": [owner_id]}).status_code == 422
    assert client.put(path, json={"doctor_ids": [owner_id]}).status_code == 422
    assert client.get(path).json() == []
    assignment_id = assign(client, actor, interview_id, second_id)
    actor.id = second_id
    actor.role = UserRole.DOCTOR
    base = f"/doctor-assignments/{assignment_id}"
    assert client.post(base + "/start").status_code == 200
    assert client.post(base + "/submit", json=payload(4)).status_code == 200
    actor.id = admin_id
    actor.role = UserRole.ADMIN
    db.get(UserDB, owner_id).role = UserRole.ADMIN
    db.commit()
    assert client.post(path, json={"doctor_ids": [second_id]}).status_code == 409


def test_bulk_assignment_selection_is_atomic_and_locks_started_ratings(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    first_id = actor.id
    first = assign(client, actor, interview_id)
    assign(client, actor, interview_id, second_id)
    actor.role = UserRole.DOCTOR
    client.post(f"/doctor-assignments/{first}/start")
    actor.role = UserRole.ADMIN
    path = f"/medical-interviews/{interview_id}/doctor-assignments"
    assert client.put(path, json={"doctor_ids": [second_id]}).status_code == 409
    assert len(client.get(path).json()) == 2
    assert client.put(path, json={"doctor_ids": [first_id, -1]}).status_code == 422
    assert len(client.get(path).json()) == 2
    saved = client.put(path, json={"doctor_ids": [first_id]})
    assert saved.status_code == 200, saved.text
    assert [item["doctor_id"] for item in saved.json()] == [first_id]
    assert client.put(path, json={"doctor_ids": [first_id, first_id]}).status_code == 422
    assert client.put(path, json={"doctor_ids": []}).status_code == 409


def test_reviewer_options_include_pending_assignments_without_private_drafts(grading_api):
    client, actor, db, interview_id, second_id = grading_api
    first = assign(client, actor, interview_id)
    assign(client, actor, interview_id, second_id)
    rows = client.get(f"/medical-interviews/{interview_id}/reviewers")
    assert rows.status_code == 200
    assert len(rows.json()) == 2
    assert all(item["rating_id"] is None for item in rows.json())
    actor.role = UserRole.DOCTOR
    assert client.get(f"/medical-interviews/{interview_id}/reviewers").status_code == 403
    client.post(f"/doctor-assignments/{first}/start")
    client.put(f"/doctor-assignments/{first}/draft", json=payload(2))
    assert client.get(f"/medical-interviews/{interview_id}/reviewers").status_code == 403
    client.post(f"/doctor-assignments/{first}/submit", json=payload(2))
    rows = client.get(f"/medical-interviews/{interview_id}/reviewers").json()
    assert len(rows) == 1
    assert rows[0]["rating_id"] is not None
    assert all("results" not in item and "rubric" not in item for item in rows)


def test_pending_assignment_selection_can_be_cleared(grading_api):
    client, actor, _, interview_id, _ = grading_api
    assign(client, actor, interview_id)
    response = client.put(f"/medical-interviews/{interview_id}/doctor-assignments", json={"doctor_ids": []})
    assert response.status_code == 200
    assert response.json() == []


def test_unified_doctor_history_preserves_order_scope_and_private_scores(grading_api):
    from app.models.medical_interview import InterviewStatus
    client, actor, db, interview_id, second_id = grading_api
    assignment_id = assign(client, actor, interview_id)
    other_assignment_id = assign(client, actor, interview_id, second_id)
    actor.role = UserRole.DOCTOR
    actor_id = actor.id
    actor.id = second_id
    other_path = f'/doctor-assignments/{other_assignment_id}'
    assert client.post(other_path + '/start').status_code == 200
    assert client.post(other_path + '/submit', json=payload(5)).status_code == 200
    actor.id = actor_id
    interview = db.get(MedicalInterviewDB, interview_id)
    interview.interview_metadata = {'private_analysis': 'AUTOMATIC_SECRET'}
    db.commit()
    own_ids = {item.id for item in db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.user_id == actor.id, MedicalInterviewDB.start_time.isnot(None)).all()}
    response = client.get('/medical-interviews')
    assert response.status_code == 200, response.text
    items = response.json()
    assert {item['id'] for item in items} == own_ids | {interview_id}
    assert len(items) == len(own_ids) + 1
    assert 'AUTOMATIC_SECRET' not in response.text
    assigned = next(item for item in items if item['id'] == interview_id)
    assert assigned['is_assigned'] is True
    assert assigned['total_duration'] == 1
    assert assigned['manual_rating_status'] == 'pending'
    assert assigned['evaluation_score'] is None
    pages = [client.get(f'/medical-interviews?skip={index}&limit=1').json()[0]['id'] for index in range(len(items))]
    assert pages == [item['id'] for item in items]
    assert pages == sorted(pages, reverse=True)
    assert client.delete(f'/medical-interviews/{interview_id}').status_code == 404
    path = f'/doctor-assignments/{assignment_id}'
    assert client.post(path + '/start').status_code == 200
    assert client.post(path + '/submit', json=payload(0)).status_code == 200
    assigned = next(item for item in client.get('/medical-interviews').json() if item['id'] == interview_id)
    assert assigned['manual_rating_status'] == 'submitted'
    assert assigned['evaluation_score'] == 4.5
