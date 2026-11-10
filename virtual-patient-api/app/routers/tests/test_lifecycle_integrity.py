"""HTTP lifecycle and rollback guarantees in an isolated schema of existing PostgreSQL."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import asyncio
import json
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, engine, get_db, SQLALCHEMY_DATABASE_URL
from app.core.auth import get_current_active_user
from app.models.user import UserDB, UserRole
from app.models.organization import OrganizationDB
from app.models.clinical_case import ClinicalCaseDB
from app.models.medical_interview import MedicalInterviewDB, InterviewStatus, InterviewRecordingDB, InterviewMediaAssetDB, InterviewTurnDB, TurnVideoAnalysisDB
from app.models.processing_job import InterviewProcessingJobDB
from app.routers import medical_interviews as interviews
from app.routers import interview_recordings as recordings
from app.routers import interview_messages as messages
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.routers.tests.test_interview_calibration import calibration_payload
from app.media.storage import LocalMediaStorage, get_media_storage
from fastapi import UploadFile


@pytest.fixture
def lifecycle_api(tmp_path):
    schema = "test_stage4_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"}).execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(test_engine)
        with Session(test_engine) as db:
            assert db.scalar(text("SELECT current_schema()")) == schema
            organization = OrganizationDB(name="Synthetic lifecycle " + uuid4().hex, active=True)
            db.add(organization); db.flush()
            user = UserDB(name="Synthetic lifecycle", email=uuid4().hex + "@example.org", hashed_password="unused", role=UserRole.STUDENT, organization_id=organization.id)
            case = ClinicalCaseDB(title="Synthetic lifecycle", description="Test only")
            db.add_all([user, case]); db.flush()
            interview = MedicalInterviewDB(user_id=user.id, clinical_case_id=case.id,
                status=InterviewStatus.IN_PROGRESS, interview_metadata={"calibration": calibration_payload()})
            db.add(interview); db.commit()
            actor = SimpleNamespace(id=user.id, role=UserRole.STUDENT, organization_id=organization.id, preferred_language="en")
            identifier, case_id = interview.id, case.id
        app = FastAPI()
        for router in (interviews.router, recordings.router, messages.router):
            app.include_router(router)
        def database():
            with Session(test_engine) as session:
                yield session
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_active_user] = lambda: actor
        app.dependency_overrides[recordings._current_media_user] = lambda: actor
        storage = LocalMediaStorage(tmp_path)
        app.dependency_overrides[get_media_storage] = lambda: storage
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, engine=test_engine, id=identifier, actor=actor, case_id=case_id, storage=storage)
    finally:
        test_engine.dispose()
        assert schema.startswith("test_stage4_") and len(schema) == 44
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
def test_two_precreated_drafts_cannot_both_start(lifecycle_api, role):
    state = lifecycle_api
    state.actor.role = role
    with Session(state.engine) as db:
        second = MedicalInterviewDB(user_id=state.actor.id, clinical_case_id=state.case_id,
            status=InterviewStatus.IN_PROGRESS, interview_metadata={"calibration": calibration_payload()})
        db.add(second); db.commit(); second_id = second.id
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    repeated = state.client.post(f"/medical-interviews/{state.id}/start")
    assert repeated.status_code == 200
    assert state.client.post(f"/medical-interviews/{second_id}/start").status_code == 409
    active = state.client.get("/medical-interviews/my/active")
    assert active.status_code == 200 and active.json()["id"] == state.id
    creation = state.client.post("/medical-interviews", json={"clinical_case_id": state.case_id})
    assert creation.status_code == 409


@pytest.mark.parametrize("language, greeting", [("es", "Hola, mucho gusto."), ("en", "Hello, nice to meet you.")])
def test_start_persists_one_opening_patient_turn(lifecycle_api, language, greeting):
    state = lifecycle_api
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, "patient_response_language": language}
        db.commit()
    for _ in range(2):
        assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    response = state.client.get(f"/medical-interviews/{state.id}/messages")
    assert response.status_code == 200
    history = response.json()["messages"]
    assert len(history) == 1
    assert history[0]["sender_type"] == "patient"
    assert history[0]["content"] == greeting


@pytest.mark.parametrize("status", [InterviewStatus.COMPLETED, InterviewStatus.PROCESSING])
def test_abandon_cannot_revert_a_frozen_interview(lifecycle_api, status):
    state = lifecycle_api
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = status
        interview.start_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
    response = state.client.post(f"/medical-interviews/{state.id}/abandon")
    assert response.status_code == 409
    with Session(state.engine) as db:
        assert db.get(MedicalInterviewDB, state.id).status == status


def test_general_update_cannot_change_lifecycle_time(lifecycle_api):
    state = lifecycle_api
    response = state.client.post(f"/medical-interviews/{state.id}", json={"end_time": datetime.now(timezone.utc).isoformat()})
    assert response.status_code == 422
    with Session(state.engine) as db:
        assert db.get(MedicalInterviewDB, state.id).end_time is None


@pytest.fixture
def exchange_agent(monkeypatch):
    async def generate(**kwargs):
        return {"agent_response": "Synthetic patient reply",
            "agent_message_object": SimpleNamespace(message_metadata={}),
            "user_message_object": SimpleNamespace(content=kwargs["user_message_content"], message_metadata={})}
    operation = AsyncMock(side_effect=generate)
    monkeypatch.setattr(messages, "VirtualPatientController", lambda: SimpleNamespace(process_user_message=operation))
    monkeypatch.setattr(messages, "persist_patient_audio", lambda *_: SimpleNamespace(synthesis_metadata={}, audio_url=None))
    return operation, generate


def test_repeated_message_request_returns_the_original_exchange(lifecycle_api, exchange_agent):
    state = lifecycle_api
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    payload = {"content": "Repeated words are allowed", "client_request_id": str(uuid4())}
    first = state.client.post(f"/medical-interviews/{state.id}/messages", json=payload)
    repeated = state.client.post(f"/medical-interviews/{state.id}/messages", json=payload)
    assert first.status_code == repeated.status_code == 200
    assert first.json()["new_message_ids"] == repeated.json()["new_message_ids"]
    assert len(repeated.json()["messages"]) == 3
    assert exchange_agent[0].await_count == 1
    payload["client_request_id"] = str(uuid4())
    distinct = state.client.post(f"/medical-interviews/{state.id}/messages", json=payload)
    assert len(distinct.json()["messages"]) == 5


def test_completion_cannot_overtake_accepted_generation(lifecycle_api, exchange_agent):
    state = lifecycle_api
    entered, release = Event(), Event()
    async def delayed(**kwargs):
        entered.set()
        assert await asyncio.to_thread(release.wait, 10)
        return await exchange_agent[1](**kwargs)
    exchange_agent[0].side_effect = delayed
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(state.client.post, f"/medical-interviews/{state.id}/messages", json={"content": "Synthetic pending"})
        assert entered.wait(10)
        try:
            closing = state.client.post(f"/medical-interviews/{state.id}/complete")
            assert closing.status_code == 409
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 200


def test_interview_history_reports_review_progress_until_completed(lifecycle_api):
    state = lifecycle_api
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = InterviewStatus.PROCESSING
        recording = InterviewRecordingDB(
            medical_interview_id=state.id, status="ready", duration_ms=1000,
            started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc),
            capture_config={}, consent_policy_version="synthetic-test",
        )
        db.add(recording)
        previous_progress = -1
        for stage in ("queued", "nonverbal_extraction", "finished"):
            recording.capture_config = {"observation_processing": {"stage": stage}}
            db.commit()
            response = state.client.get("/medical-interviews")
            assert response.status_code == 200
            row, = response.json()
            assert row["status"] == "processing"
            assert previous_progress < row["review_progress"] < 100
            previous_progress = row["review_progress"]

        interview.status = InterviewStatus.COMPLETED
        db.commit()
    response = state.client.get("/medical-interviews")
    assert response.status_code == 200
    row, = response.json()
    assert row["status"] == "completed"
    assert row["review_progress"] is None


def test_new_conversation_is_rejected_once_media_is_frozen(lifecycle_api, exchange_agent):
    state = lifecycle_api
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    with Session(state.engine) as db:
        db.add(InterviewRecordingDB(medical_interview_id=state.id, status="ready", duration_ms=1000,
            started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc), capture_config={}, consent_policy_version="synthetic-test"))
        db.commit()
    response = state.client.post(f"/medical-interviews/{state.id}/messages", json={"content": "Too late"})
    assert response.status_code == 409
    assert exchange_agent[0].await_count == 0


def start_capture(state):
    from app.routers import recording_segments, recording_blocks
    state.client.app.include_router(recording_segments.router)
    state.client.app.include_router(recording_blocks.router)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'recording_transport': 'reusable_blocks_v1'}
        db.commit()
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    state.segment_id = str(uuid4())
    response = state.client.post(f"/medical-interviews/{state.id}/recording/segments", json={
        'request_id': state.segment_id, 'capture_config': {}})
    assert response.status_code == 200
    state.client.headers['X-Capture-Segment'] = state.segment_id
    state.block_id = str(uuid4())
    with Session(state.engine) as db:
        return db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one().id


def media_upload(state, *, capture_config=None, preserve_only=False, **overrides):
    root = f'/medical-interviews/{state.id}/recording/blocks'
    messages = state.client.get(f'/medical-interviews/{state.id}/messages').json()['messages']
    patient = next(item for item in reversed(messages) if item['sender_type'] == 'patient')
    student = next((item for item in reversed(messages) if item['sender_type'] == 'user'), None)
    metadata = {'capture_attempt_id': state.segment_id, 'order': 0, 'duration_ms': 1000,
        'patient_message_id': patient['id'], 'patient_audio_missing': True,
        **({'student_message_id': student['id'], 'student_speech': {'start_ms': 0, 'end_ms': 400}} if student else {})}
    response = state.client.put(root + '/' + state.block_id, data={'metadata': json.dumps(metadata)},
        files={'file': ('synthetic.webm', b'synthetic original', 'video/webm')})
    assert response.status_code == 200, response.text
    covered = {patient['id'], student['id'] if student else None}
    return state.client.post(root + '/finalize', json={'block_ids': [state.block_id],
        'missing_message_ids': [item['id'] for item in messages if item['id'] not in covered]})




def test_completion_requires_finalized_media_not_just_a_recording_row(lifecycle_api):
    state = lifecycle_api
    start_capture(state)
    response = state.client.post(f"/medical-interviews/{state.id}/complete")
    assert response.status_code == 409
    with Session(state.engine) as db:
        assert db.get(MedicalInterviewDB, state.id).status == InterviewStatus.IN_PROGRESS
        assert db.query(InterviewProcessingJobDB).count() == 0














def test_completion_retry_is_idempotent_and_keeps_the_capture_clock(lifecycle_api, monkeypatch):
    state = lifecycle_api
    start_capture(state)
    monkeypatch.setattr(__import__("app.routers.recording_blocks", fromlist=["probe_media_timing"]), "probe_media_timing", lambda _: {"duration_ms": 1000, "start_pts_ms": 0, "end_pts_ms": 1000})
    assert media_upload(state).status_code == 200
    first = state.client.post(f"/medical-interviews/{state.id}/complete")
    repeated = state.client.post(f"/medical-interviews/{state.id}/complete")
    assert first.status_code == repeated.status_code == 200
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        end_time = interview.end_time
        assert interview.total_duration == 1
        assert db.query(InterviewProcessingJobDB).filter_by(kind="completion").count() == 1
        controller = MedicalInterviewController(db)
        controller.interrupt_processing(state.id)
        assert interview.end_time == end_time
        job = db.query(InterviewProcessingJobDB).filter_by(kind="completion").one()
        job.status = "failed"
        db.commit()
    retried = state.client.post(f"/medical-interviews/{state.id}/complete")
    assert retried.status_code == 200
    with Session(state.engine) as db:
        controller = MedicalInterviewController(db)
        controller.complete_interview(state.id)
        interview = db.get(MedicalInterviewDB, state.id)
        assert interview.end_time == end_time
        assert interview.total_duration == 1
        assert controller.get_average_duration_for_user(state.actor.id)["average_duration_seconds"] == 1




def test_final_summary_is_persisted_once_for_the_frozen_last_message(lifecycle_api, monkeypatch):
    from app.controllers.summary_controller import SummaryController
    from app.models.medical_interview.interview_message import InterviewMessageDB
    from app.models.medical_interview.progress_summary import ProgressSummaryDB
    state = lifecycle_api
    with Session(state.engine) as db:
        message = InterviewMessageDB(interview_id=state.id, sender_type="user", content="Synthetic final content")
        db.add(message); db.commit()
        data = MedicalInterviewController(db).get_interview_evaluation_data(state.id)
        formatted = MedicalInterviewController(db).format_messages_for_evaluation(data["messages"])
        generate = AsyncMock(return_value={"summary_result": {"summary_text": "Synthetic final summary"}})
        monkeypatch.setattr(SummaryController, "process_summary", generate)
        asyncio.run(interviews._ensure_final_summary(db, state.id, data, formatted))
        asyncio.run(interviews._ensure_final_summary(db, state.id, data, formatted))
        assert generate.await_count == 1
        persisted = db.query(ProgressSummaryDB).one()
        assert persisted.last_updated_message_id == message.id
        assert persisted.source_language == "en"
        assert persisted.summary_text == "Synthetic final summary"


@pytest.mark.parametrize("aspects", [[], ["show_interest"], ["show_interest"] * 6])
def test_incomplete_text_control_is_rejected_before_storage(aspects):
    from app.agents.schemas.evaluation import EvaluationResult
    from app.multimodal.evaluation_service import validate_text_control
    with pytest.raises(ValueError, match="exactly the six"):
        validate_text_control([EvaluationResult(aspect=aspect, score=4, feedback="Synthetic valid response") for aspect in aspects])


@pytest.mark.parametrize("initial_control_complete", [True, False])
def test_durable_completion_retry_preserves_control_snapshot_and_frozen_media(lifecycle_api, monkeypatch, exchange_agent, initial_control_complete):
    from app.controllers.summary_controller import SummaryController
    from app.multimodal import processing_jobs as jobs
    from app.multimodal.evaluation_service import EVALUATION_CATEGORY_ORDER, evaluate_and_store_multimodal
    from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB, InterviewEvaluationRunDB
    from app.agents.schemas.evaluation import EvaluationResult
    state = lifecycle_api
    start_capture(state)
    assert state.client.post(f"/medical-interviews/{state.id}/messages", json={"content": "Synthetic frozen transcript", "segment_id": state.segment_id}).status_code == 200
    monkeypatch.setattr(__import__("app.routers.recording_blocks", fromlist=["probe_media_timing"]), "probe_media_timing", lambda _: {"duration_ms": 1000, "start_pts_ms": 0, "end_pts_ms": 1000})
    assert media_upload(state).status_code == 200
    factory = sessionmaker(bind=state.engine)
    monkeypatch.setattr(interviews, "SessionLocal", factory)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(jobs, "engine", state.engine)
    summary = AsyncMock(return_value={"summary_result": {"summary_text": "Synthetic final summary"}})
    monkeypatch.setattr(SummaryController, "process_summary", summary)
    agent = SimpleNamespace(evaluation_prompts={}, llm=None, run_provenance=[],
        evaluate_all_aspects=AsyncMock(return_value=[EvaluationResult(aspect=aspect, score=4, feedback="Synthetic control") for aspect in (EVALUATION_CATEGORY_ORDER if initial_control_complete else ["show_interest"])]),
        evaluate_multimodal=AsyncMock())
    monkeypatch.setattr(interviews, "EvaluationAgent", lambda **_: agent)
    monkeypatch.setattr(interviews, "_wait_for_multimodal_analysis", AsyncMock(return_value="partial"))
    async def fail_enrichment(*args, **kwargs):
        raise RuntimeError("Synthetic processing failure after control commit")
    monkeypatch.setattr(interviews, "evaluate_and_store_multimodal", fail_enrichment)
    assert state.client.post(f"/medical-interviews/{state.id}/complete").status_code == 200
    with factory() as db:
        first_job = db.query(InterviewProcessingJobDB).filter_by(kind="completion").one().id
        end_time = db.get(MedicalInterviewDB, state.id).end_time
        media_keys = sorted(asset.storage_key for asset in db.query(InterviewMediaAssetDB).all())
    asyncio.run(jobs._run(first_job))
    with factory() as db:
        assert db.get(InterviewProcessingJobDB, first_job).status == "failed"
        assert db.get(MedicalInterviewDB, state.id).status == InterviewStatus.INTERRUPTED
        if initial_control_complete:
            control = db.query(InterviewEvaluationDB).one()
            control_id, control_result = control.id, control.evaluation_results
            snapshot = db.query(InterviewEvaluationRunDB).one().snapshot
        else:
            assert db.query(InterviewEvaluationDB).count() == 0
            assert db.query(InterviewEvaluationRunDB).count() == 0
    agent.evaluate_all_aspects.return_value = [EvaluationResult(aspect=aspect, score=4, feedback="Synthetic control") for aspect in EVALUATION_CATEGORY_ORDER]
    monkeypatch.setattr(interviews, "evaluate_and_store_multimodal", evaluate_and_store_multimodal)
    assert state.client.post(f"/medical-interviews/{state.id}/complete").status_code == 200
    with factory() as db:
        retry_job = db.query(InterviewProcessingJobDB).filter_by(kind="completion", status="queued").one().id
    asyncio.run(jobs._run(retry_job))
    asyncio.run(jobs._run(retry_job))
    with factory() as db:
        assert db.get(InterviewProcessingJobDB, retry_job).status == "completed"
        interview = db.get(MedicalInterviewDB, state.id)
        assert interview.status == InterviewStatus.COMPLETED
        assert interview.end_time == end_time and interview.total_duration == 1
        if initial_control_complete:
            assert db.get(InterviewEvaluationDB, control_id).evaluation_results == control_result
        runs = db.query(InterviewEvaluationRunDB).all()
        assert len(runs) == 2
        if initial_control_complete:
            assert next(run.snapshot for run in runs if run.evaluation_condition == "TEXT_ONLY") == snapshot
        assert sorted(asset.storage_key for asset in db.query(InterviewMediaAssetDB).all()) == media_keys
        assert db.query(InterviewEvaluationDB).count() == 2
    assert agent.evaluate_all_aspects.await_count == (1 if initial_control_complete else 2)
    assert summary.await_count == 1
    agent.evaluate_multimodal.assert_not_awaited()


