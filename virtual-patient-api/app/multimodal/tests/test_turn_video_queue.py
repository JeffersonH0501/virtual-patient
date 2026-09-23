"""Persistence tests for durable per-turn visual analysis jobs."""

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
