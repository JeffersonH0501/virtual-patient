"""Queue transactions preserve recoverable work and prevent active duplicates."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError
from app.models.processing_job import InterviewProcessingJobDB
from app.multimodal import processing_jobs
from app.multimodal.processing_jobs import stage_processing_job
from app.routers.tests.test_lifecycle_integrity import lifecycle_api


def test_jobs_commit_atomically_and_active_duplicates_are_rejected():
    engine = create_engine("sqlite://")
    InterviewProcessingJobDB.__table__.create(engine)
    with Session(engine) as db:
        stage_processing_job(db, 7, "evaluation", {"recording_id": "fixture"})
        db.rollback()
        assert db.query(InterviewProcessingJobDB).count() == 0
        first = stage_processing_job(db, 7, "evaluation", {"recording_id": "fixture"})
        db.commit()
        stage_processing_job(db, 7, "evaluation", {"recording_id": "fixture"})
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        first.status = "completed"
        db.commit()
        stage_processing_job(db, 7, "evaluation", {"recording_id": "fixture"})
        db.commit()
        assert db.query(InterviewProcessingJobDB).count() == 2
    engine.dispose()


def test_completion_waits_for_media_even_when_queued_first(lifecycle_api, monkeypatch):
    factory = sessionmaker(bind=lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "engine", lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "SessionLocal", factory)
    monkeypatch.setattr(processing_jobs, "_succeeded", lambda *_: True)
    calls = []
    async def dispatch(kind, *_):
        calls.append(kind)
    monkeypatch.setattr(processing_jobs, "_dispatch", dispatch)
    with factory() as db:
        for kind in ("completion", "pipeline"):
            stage_processing_job(db, lifecycle_api.id, kind, {"recording_id": "fixture"})
            db.commit()
    asyncio.run(processing_jobs._run_next())
    asyncio.run(processing_jobs._run_next())
    assert calls == ["pipeline", "completion"]


def test_a_running_job_does_not_block_another_process_from_starting_the_next(lifecycle_api, monkeypatch):
    # The shared slot lock guards only selection; a slow job must not keep other
    # jobs from starting. Job exclusivity is enforced by the per-job lock in _run.
    factory = sessionmaker(bind=lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "engine", lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "SessionLocal", factory)
    monkeypatch.setattr(processing_jobs, "CANDIDATE_BATCH_SIZE", 2)
    monkeypatch.setattr(processing_jobs, "_succeeded", lambda *_: True)
    with factory() as db:
        for kind in ("pipeline", "observations"):
            stage_processing_job(db, lifecycle_api.id, kind, {"recording_id": "fixture"})
            db.commit()

    async def scenario():
        entered = asyncio.Queue()
        release = asyncio.Event()

        async def dispatch(kind, *_):
            await entered.put(kind)
            if kind == "pipeline":
                await release.wait()  # Hold the first job open.

        monkeypatch.setattr(processing_jobs, "_dispatch", dispatch)
        first = asyncio.create_task(processing_jobs._run_next())
        try:
            # The pipeline job is now running (held open).
            assert await asyncio.wait_for(entered.get(), 5) == "pipeline"
            # A second runner starts the next job even though the first still runs.
            await asyncio.wait_for(processing_jobs._run_next(), 5)
            assert await asyncio.wait_for(entered.get(), 5) == "observations"
        finally:
            release.set()
            await first

    asyncio.run(scenario())


def test_transient_failure_is_retried_then_terminally_failed(lifecycle_api, monkeypatch):
    # A failing job must be requeued up to MAX_JOB_ATTEMPTS before it is marked
    # failed, so one transient crash does not permanently lose the analysis.
    factory = sessionmaker(bind=lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "engine", lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "SessionLocal", factory)
    monkeypatch.setattr(processing_jobs, "MAX_JOB_ATTEMPTS", 3)
    monkeypatch.setattr(processing_jobs, "_close_failed_phases", lambda *_: None)

    async def always_fail(*_):
        raise RuntimeError("Mock transient failure")

    monkeypatch.setattr(processing_jobs, "_dispatch", always_fail)
    with factory() as db:
        stage_processing_job(db, lifecycle_api.id, "replay_preview", {"recording_id": "fixture"})
        db.commit()

    def status_and_attempts():
        with factory() as db:
            row = db.query(InterviewProcessingJobDB).filter_by(medical_interview_id=lifecycle_api.id).first()
            return row.status, row.attempts

    asyncio.run(processing_jobs._run_next())
    assert status_and_attempts() == ("queued", 1)  # Requeued, not lost.
    asyncio.run(processing_jobs._run_next())
    assert status_and_attempts() == ("queued", 2)
    asyncio.run(processing_jobs._run_next())
    assert status_and_attempts() == ("failed", 3)  # Terminal only after retries.


def test_observations_job_requires_both_phases_to_finish():
    db = Mock()
    recording = db.query.return_value.filter.return_value.first.return_value
    recording.capture_config = {
        "observation_processing": {"status": "complete"},
        "evaluation_processing": {"status": "failed"},
    }
    job = SimpleNamespace(kind="observations", payload={"recording_id": "fixture"})
    assert not processing_jobs._succeeded(db, job)
    recording.capture_config["evaluation_processing"]["status"] = "unavailable"
    assert processing_jobs._succeeded(db, job)


def test_failed_observation_job_closes_only_unfinished_phases():
    db = Mock()
    recording = db.get.return_value
    recording.capture_config = {
        "observation_processing": {"status": "complete"},
        "evaluation_processing": {"status": "processing"},
    }
    job = SimpleNamespace(kind="observations", payload={"recording_id": "fixture"})

    processing_jobs._close_failed_phases(db, job)

    assert recording.capture_config == {
        "observation_processing": {"status": "complete"},
        "evaluation_processing": {"status": "failed", "stage": "finished", "reason": "technical_processing_failure"},
    }
