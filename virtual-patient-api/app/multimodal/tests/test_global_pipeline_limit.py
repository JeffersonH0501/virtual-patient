"""PostgreSQL pipeline slots must bound independent runners and survive cancellation."""
import asyncio
from unittest.mock import Mock
from io import StringIO
from uuid import uuid4
import sys
from sqlalchemy.orm import sessionmaker
from app.multimodal import processing_jobs
from app.models.processing_job import InterviewProcessingJobDB
from app.multimodal import process_isolation as isolation
from app.routers.tests.test_lifecycle_integrity import lifecycle_api


def test_global_slots_bound_connections_and_release_after_cancellation(lifecycle_api, monkeypatch):
    monkeypatch.setattr(isolation, "engine", lifecycle_api.engine)
    monkeypatch.setattr(isolation, "PIPELINE_LOCK_BASE", int(uuid4().hex[:10], 16))
    async def scenario():
        entered = []
        release = asyncio.Event()
        async def run(index):
            async with isolation._database_pipeline_slot():
                entered.append(index)
                await release.wait()
        first, second, third = [asyncio.create_task(run(index)) for index in range(3)]
        try:
            await asyncio.sleep(.2)
            assert entered == [0, 1]
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
            for _ in range(30):
                if 2 in entered:
                    break
                await asyncio.sleep(.05)
            assert entered == [0, 1, 2]
        finally:
            release.set()
            await asyncio.gather(first, second, third, return_exceptions=True)
        async with isolation.pipeline_slot():
            pass
    asyncio.run(scenario())


def test_dead_native_worker_still_closes_owned_streams():
    from app.multimodal.turn_video_queue import _PersistentTurnVideoWorker
    worker = object.__new__(_PersistentTurnVideoWorker)
    worker.process = Mock(stdin=StringIO(), stdout=StringIO())
    worker.process.poll.return_value = 1
    worker.close()
    assert worker.process.stdin.closed and worker.process.stdout.closed


def test_broken_input_pipe_does_not_prevent_output_pipe_cleanup():
    from app.multimodal.turn_video_queue import _PersistentTurnVideoWorker
    worker = object.__new__(_PersistentTurnVideoWorker)
    worker.process = Mock(stdin=Mock(), stdout=StringIO())
    worker.process.poll.return_value = 1
    worker.process.stdin.close.side_effect = BrokenPipeError("Synthetic broken pipe")
    worker.close()
    assert worker.process.stdout.closed


def test_cancelled_runner_leaves_durable_work_recoverable(lifecycle_api, monkeypatch):
    factory = sessionmaker(bind=lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "engine", lifecycle_api.engine)
    monkeypatch.setattr(processing_jobs, "SessionLocal", factory)
    monkeypatch.setattr(processing_jobs, "_succeeded", lambda *_: True)
    with factory() as db:
        job = processing_jobs.stage_processing_job(db, lifecycle_api.id, "evaluation", {"recording_id": "synthetic"})
        db.commit()
        identifier = job.id
    async def scenario():
        started = asyncio.Event()
        async def pending(*_):
            started.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(processing_jobs, "_dispatch", pending)
        task = asyncio.create_task(processing_jobs._run(identifier))
        await asyncio.wait_for(started.wait(), 10)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        with factory() as db:
            assert db.get(InterviewProcessingJobDB, identifier).status == "processing"
        async def finish(*_):
            pass
        monkeypatch.setattr(processing_jobs, "_dispatch", finish)
        await processing_jobs._run(identifier)
    asyncio.run(scenario())
    with factory() as db:
        job = db.get(InterviewProcessingJobDB, identifier)
        assert job.status == "completed" and job.attempts == 2


def test_cancellation_reaps_the_actual_child_before_releasing_capacity(lifecycle_api, monkeypatch):
    monkeypatch.setattr(isolation, "engine", lifecycle_api.engine)
    monkeypatch.setattr(isolation, "PIPELINE_LOCK_BASE", int(uuid4().hex[:10], 16))
    original = asyncio.create_subprocess_exec
    async def scenario():
        started = asyncio.Event()
        children = []
        async def spawn(*_args, **_kwargs):
            child = await original(sys.executable, "-c", "import time; time.sleep(60)")
            children.append(child)
            started.set()
            return child
        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        task = asyncio.create_task(isolation.process_multimodal_interview_isolated(7, "synthetic"))
        await asyncio.wait_for(started.wait(), 10)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert children[0].returncode is not None
        async with isolation.pipeline_slot():
            pass
    asyncio.run(scenario())


def test_waiting_requests_do_not_exhaust_the_connection_pool(lifecycle_api, monkeypatch):
    from sqlalchemy import create_engine
    bounded = create_engine(lifecycle_api.engine.url, pool_size=2, max_overflow=0, pool_timeout=.1)
    monkeypatch.setattr(isolation, "engine", bounded)
    monkeypatch.setattr(isolation, "PIPELINE_LOCK_BASE", int(uuid4().hex[:10], 16))
    async def scenario():
        async def run():
            async with isolation.pipeline_slot():
                await asyncio.sleep(.05)
        outcomes = await asyncio.gather(*(run() for _ in range(5)), return_exceptions=True)
        assert not any(isinstance(result, BaseException) for result in outcomes), outcomes
    try:
        asyncio.run(scenario())
    finally:
        bounded.dispose()


def test_pipeline_stage_preserves_concurrent_feedback_and_manifests(lifecycle_api):
    from sqlalchemy.orm import Session
    from datetime import datetime, timezone
    from uuid import uuid4
    from app.models.medical_interview import InterviewRecordingDB
    from app.multimodal.pipeline import _set_stage
    from app.multimodal.extraction_provenance import record_extraction_manifest
    with Session(lifecycle_api.engine) as initial:
        recording = InterviewRecordingDB(id=str(uuid4()), medical_interview_id=lifecycle_api.id,
            started_at=datetime.now(timezone.utc), capture_config={}, consent_policy_version="synthetic")
        initial.add(recording)
        initial.commit()
        identifier = recording.id
    with Session(lifecycle_api.engine) as extraction, Session(lifecycle_api.engine) as feedback:
        stale = extraction.get(InterviewRecordingDB, identifier)
        manifest_hash = record_extraction_manifest(stale, {"manifest_version": "extraction_v1"})
        other = feedback.query(InterviewRecordingDB).filter_by(id=identifier).with_for_update().one()
        other.capture_config = {"learning_moments": {"status": "completed", "generation_id": "synthetic"}}
        feedback.commit()
        _set_stage(extraction, stale, "processing", "thresholding")
    with Session(lifecycle_api.engine) as check:
        capture = check.get(InterviewRecordingDB, identifier).capture_config
        assert capture["learning_moments"]["generation_id"] == "synthetic"
        assert capture["extraction_manifests"][manifest_hash]["manifest_version"] == "extraction_v1"
