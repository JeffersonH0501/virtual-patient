"""Lifecycle tests for the per-turn single-consumer FIFO."""

from threading import enumerate as enumerate_threads
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from app.multimodal import turn_video_queue
from app.multimodal.constants import NONVERBAL_GAZE_QUEUE_CAPACITY
from app.models.medical_interview import TurnVideoAnalysisStatus


class _FakeQuery:
    def __init__(self, jobs):
        self.jobs = jobs

    def filter(self, *args):
        return self

    def first(self):
        return self.jobs[0] if self.jobs else None

    def all(self):
        return self.jobs


class _FakeSession:
    def __init__(self, jobs):
        self.jobs = jobs
        self.committed_statuses = []

    def query(self, model):
        return _FakeQuery(self.jobs)

    def commit(self):
        self.committed_statuses.append(self.jobs[0].status)

    def rollback(self):
        return None

    def close(self):
        return None


def test_fifo_is_non_blocking_and_isolates_one_job_failure(monkeypatch):
    processed: list[str] = []
    worker_instances = []

    class FakeWorker:
        def __init__(self):
            worker_instances.append(self)

        def process_job(self, job_id):
            processed.append(job_id)
            if job_id == "turn-2":
                raise RuntimeError("native failure")
            return "completed"

        def close(self):
            return None

    monkeypatch.setattr(turn_video_queue, "_PersistentTurnVideoWorker", FakeWorker)
    monkeypatch.setattr(turn_video_queue, "_mark_job_failed", lambda *args: None)
    turn_video_queue.start_turn_video_worker(recover=False)
    started = perf_counter()
    for job_id in ("turn-1", "turn-2", "turn-3"):
        turn_video_queue.enqueue_turn_video_analysis(job_id)
    enqueue_ms = (perf_counter() - started) * 1000
    turn_video_queue._jobs.join()
    turn_video_queue.shutdown_turn_video_worker(timeout=2)

    assert enqueue_ms < 100
    assert processed == ["turn-1", "turn-2", "turn-3"]
    assert len(worker_instances) == 2
    assert not any(
        thread.name == "turn-video-analysis-worker" for thread in enumerate_threads()
    )


def test_release_command_closes_models_after_previously_queued_jobs(monkeypatch):
    events: list[str] = []

    class FakeWorker:
        def process_job(self, job_id):
            events.append(f"process:{job_id}")
            return "completed"

        def close(self):
            events.append("close")

    monkeypatch.setattr(turn_video_queue, "_PersistentTurnVideoWorker", FakeWorker)
    turn_video_queue.start_turn_video_worker(recover=False)
    turn_video_queue.enqueue_turn_video_analysis("turn-1")
    turn_video_queue.enqueue_turn_video_analysis("turn-2")
    turn_video_queue.release_turn_video_worker_resources()
    turn_video_queue._jobs.join()
    turn_video_queue.shutdown_turn_video_worker(timeout=2)

    assert events == ["process:turn-1", "process:turn-2", "close"]


def test_calibration_and_turn_jobs_reuse_the_same_visual_worker(monkeypatch):
    events: list[str] = []
    worker_instances = []

    class FakeWorker:
        def __init__(self):
            worker_instances.append(self)

        def process_calibration(self, request_id, stage, media_path, metadata):
            events.append(f"calibration:{stage}")
            return {"passed": True}

        def process_job(self, job_id):
            events.append(f"turn:{job_id}")
            return "completed"

        def close(self):
            events.append("close")

    monkeypatch.setattr(turn_video_queue, "_PersistentTurnVideoWorker", FakeWorker)
    turn_video_queue.start_turn_video_worker(recover=False)
    gaze = turn_video_queue.enqueue_calibration_visual_analysis(
        "gaze-request", "gaze", Path("gaze.webm"), {"targets": []}
    )
    camera = turn_video_queue.enqueue_calibration_visual_analysis(
        "camera-request", "camera", Path("camera.webm"), {"affine_matrix": []}
    )
    turn_video_queue.enqueue_turn_video_analysis("turn-1")
    turn_video_queue.release_turn_video_worker_resources()
    turn_video_queue._jobs.join()
    turn_video_queue.shutdown_turn_video_worker(timeout=2)

    assert gaze.result(timeout=0) == {"passed": True}
    assert camera.result(timeout=0) == {"passed": True}
    assert events == ["calibration:gaze", "calibration:camera", "turn:turn-1", "close"]
    assert len(worker_instances) == 1


def _job(status=TurnVideoAnalysisStatus.QUEUED.value):
    return SimpleNamespace(
        id="job-1",
        medical_interview_id=1,
        turn_id="turn-1",
        speaker="student",
        start_ms=0,
        end_ms=1000,
        storage_key="turn.webm",
        roi_snapshots=[],
        queued_at=None,
        started_at=None,
        completed_at=None,
        error=None,
        result=None,
        status=status,
    )


def test_job_transitions_from_queued_through_processing_to_completed(monkeypatch):
    job = _job()
    session = _FakeSession([job])
    observed_queue_capacities = []
    storage = SimpleNamespace(resolve=lambda key: key, delete=lambda key: None)
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    monkeypatch.setattr(turn_video_queue, "get_media_storage", lambda: storage)
    monkeypatch.setattr(turn_video_queue, "read_calibration_profile", lambda interview: None)
    monkeypatch.setattr(turn_video_queue, "create_tracker", lambda **kwargs: object())
    monkeypatch.setattr(
        turn_video_queue,
        "extract_nonverbal_video_observations_parallel",
        lambda *args, **kwargs: observed_queue_capacities.append(kwargs["queue_capacity"]) or [],
    )
    monkeypatch.setattr(
        turn_video_queue,
        "analyze_nods",
        lambda observations: SimpleNamespace(),
    )
    monkeypatch.setattr(
        turn_video_queue,
        "build_turn_raw_features",
        lambda *args, **kwargs: SimpleNamespace(model_dump=lambda **options: {"ok": True}),
    )

    turn_video_queue._process_job(job.id)

    assert session.committed_statuses == [
        TurnVideoAnalysisStatus.PROCESSING.value,
        TurnVideoAnalysisStatus.COMPLETED.value,
    ]
    assert observed_queue_capacities == [NONVERBAL_GAZE_QUEUE_CAPACITY]


def test_job_transitions_from_processing_to_failed_on_error(monkeypatch):
    job = _job(TurnVideoAnalysisStatus.PROCESSING.value)
    session = _FakeSession([job])
    storage = SimpleNamespace(resolve=lambda key: (_ for _ in ()).throw(OSError("broken video")))
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    monkeypatch.setattr(turn_video_queue, "get_media_storage", lambda: storage)
    monkeypatch.setattr(turn_video_queue, "read_calibration_profile", lambda interview: None)
    monkeypatch.setattr(turn_video_queue, "create_tracker", lambda **kwargs: object())

    turn_video_queue._process_job(job.id)

    assert session.committed_statuses == [
        TurnVideoAnalysisStatus.PROCESSING.value,
        TurnVideoAnalysisStatus.FAILED.value,
    ]
    assert job.error == "broken video"


def test_startup_requeues_queued_and_processing_jobs(monkeypatch):
    jobs = [
        _job(TurnVideoAnalysisStatus.QUEUED.value),
        _job(TurnVideoAnalysisStatus.PROCESSING.value),
    ]
    jobs[1].id = "job-2"
    session = _FakeSession(jobs)
    queued_ids = []
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    monkeypatch.setattr(turn_video_queue, "_ensure_worker", lambda: None)
    monkeypatch.setattr(
        turn_video_queue,
        "_jobs",
        SimpleNamespace(put=queued_ids.append),
    )

    turn_video_queue.start_turn_video_worker(recover=True)

    assert [job.status for job in jobs] == [
        TurnVideoAnalysisStatus.QUEUED.value,
        TurnVideoAnalysisStatus.QUEUED.value,
    ]
    assert queued_ids == ["job-1", "job-2"]
