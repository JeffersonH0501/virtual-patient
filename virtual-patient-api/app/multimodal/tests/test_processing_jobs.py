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


def test_durable_jobs_wait_for_the_global_background_slot(lifecycle_api, monkeypatch):
    factory = sessionmaker(bind=lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "engine", lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "SessionLocal", factory)
    monkeypatch.setattr(processing_jobs, "CANDIDATE_BATCH_SIZE", 2)
    monkeypatch.setattr(processing_jobs, "_succeeded", lambda *_: True)
    with factory() as db:
        for kind in ("pipeline", "observations", "evaluation"):
            stage_processing_job(db, lifecycle_api.id, kind, {"recording_id": "fixture"})
            db.commit()

    async def scenario():
        entered = asyncio.Queue()
        release = asyncio.Event()

        async def dispatch(kind, *_):
            await entered.put(kind)
            if kind != "evaluation":
                await release.wait()

        monkeypatch.setattr(processing_jobs, "_dispatch", dispatch)
        first = asyncio.create_task(processing_jobs._run_next())
        try:
            assert await asyncio.wait_for(entered.get(), 5) == "pipeline"
            await asyncio.wait_for(processing_jobs._run_next(), 5)
            assert entered.empty()
            with factory() as db:
                queued = db.query(InterviewProcessingJobDB).filter_by(status="queued").count()
                assert queued == 2
        finally:
            release.set()
            await first
        await asyncio.wait_for(processing_jobs._run_next(), 5)
        assert entered.get_nowait() == "observations"
        await asyncio.wait_for(processing_jobs._run_next(), 5)
        assert entered.get_nowait() == "evaluation"

    asyncio.run(scenario())


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
