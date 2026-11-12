"""Persistence tests for durable per-turn visual analysis jobs."""

from types import SimpleNamespace

from app.multimodal import turn_video_queue
from app.multimodal.constants import NONVERBAL_GAZE_QUEUE_CAPACITY
from app.multimodal.config_loader import load_methodology_config
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


def test_interruption_keeps_raw_clip_for_later_recovery():
    job = _job()
    session = _FakeSession([job])
    assert turn_video_queue.fail_pending_turn_video_jobs(session, 1, "interview_interrupted") == 1
    assert job.status == TurnVideoAnalysisStatus.FAILED.value
    assert job.storage_key == "turn.webm"
    assert job.error == "interview_interrupted"


def test_job_transitions_from_queued_through_processing_to_completed(monkeypatch):
    job = _job()
    session = _FakeSession([job])
    observed_queue_capacities = []
    storage = SimpleNamespace(resolve=lambda key: key, delete=lambda key: None)
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    monkeypatch.setattr(turn_video_queue, "get_media_storage", lambda: storage)
    monkeypatch.setattr(turn_video_queue, "read_calibration_profile", lambda interview: None)
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
    raw = SimpleNamespace(extractor={})
    raw.model_dump = lambda **options: {"ok": True, "extractor": raw.extractor}
    monkeypatch.setattr(turn_video_queue, "build_turn_raw_features", lambda *args, **kwargs: raw)

    turn_video_queue._process_job(job.id)

    assert job.storage_key == "turn.webm"

    assert session.committed_statuses == [
        TurnVideoAnalysisStatus.PROCESSING.value,
        TurnVideoAnalysisStatus.COMPLETED.value,
    ]
    assert observed_queue_capacities == [NONVERBAL_GAZE_QUEUE_CAPACITY]
    assert job.result["extractor"]["extraction_manifest"]["methodology"]["versions"]["thresholds"] == load_methodology_config().versions.thresholds


def test_job_transitions_from_processing_to_failed_on_error(monkeypatch):
    job = _job(TurnVideoAnalysisStatus.PROCESSING.value)
    session = _FakeSession([job])
    storage = SimpleNamespace(resolve=lambda key: (_ for _ in ()).throw(OSError("broken video")))
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    monkeypatch.setattr(turn_video_queue, "get_media_storage", lambda: storage)
    monkeypatch.setattr(turn_video_queue, "read_calibration_profile", lambda interview: None)

    turn_video_queue._process_job(job.id)

    assert session.committed_statuses == [
        TurnVideoAnalysisStatus.PROCESSING.value,
        TurnVideoAnalysisStatus.FAILED.value,
    ]
    assert job.error == "broken video"


def _guard_native(monkeypatch):
    """Make native model work explode so a true skip never reaches it.

    ``_process_job`` resolves media storage before it reads the job status, so
    storage itself is provided harmlessly; the calibration/extraction calls are
    the ones a skipped job must never perform.
    """
    def explode(*args, **kwargs):
        raise AssertionError("A skipped job must not run calibration or extraction")

    monkeypatch.setattr(
        turn_video_queue, "get_media_storage",
        lambda: SimpleNamespace(resolve=explode, delete=lambda key: None),
    )
    monkeypatch.setattr(turn_video_queue, "read_calibration_profile", explode)
    monkeypatch.setattr(turn_video_queue, "extract_nonverbal_video_observations_parallel", explode)


def test_already_completed_job_is_skipped_idempotently(monkeypatch):
    # A re-poll or duplicate schedule of a finished turn must not reprocess it.
    job = _job(TurnVideoAnalysisStatus.COMPLETED.value)
    session = _FakeSession([job])
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    _guard_native(monkeypatch)

    assert turn_video_queue._process_job(job.id) == "skipped"
    assert session.committed_statuses == []
    assert job.status == TurnVideoAnalysisStatus.COMPLETED.value


def test_failed_job_is_not_reprocessed(monkeypatch):
    # A terminal failed job is never silently retried by a stray schedule.
    job = _job(TurnVideoAnalysisStatus.FAILED.value)
    session = _FakeSession([job])
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    _guard_native(monkeypatch)

    assert turn_video_queue._process_job(job.id) == "skipped"
    assert session.committed_statuses == []
    assert job.status == TurnVideoAnalysisStatus.FAILED.value


def test_missing_job_is_skipped(monkeypatch):
    # A job row deleted before the consumer reaches it must not raise.
    session = _FakeSession([])
    monkeypatch.setattr(turn_video_queue, "SessionLocal", lambda: session)
    _guard_native(monkeypatch)

    assert turn_video_queue._process_job("gone") == "skipped"
    assert session.committed_statuses == []


class _StatusFilteringSession:
    """Session whose ``all()`` honors the queued-status filter like the database.

    ``fail_pending_turn_video_jobs`` must only terminate queued jobs; a job that
    the single consumer is already processing may finish its native call safely.
    """

    def __init__(self, jobs):
        self.jobs = jobs
        self.committed = False

    def query(self, model):
        return self

    def filter(self, *args):
        del args
        return self

    def all(self):
        # Mirror the production filter: only queued jobs are returned.
        return [
            job for job in self.jobs
            if job.status == TurnVideoAnalysisStatus.QUEUED.value
        ]

    def commit(self):
        self.committed = True


def test_fail_pending_only_terminates_queued_jobs():
    queued = _job(TurnVideoAnalysisStatus.QUEUED.value)
    queued.id = "queued"
    processing = _job(TurnVideoAnalysisStatus.PROCESSING.value)
    processing.id = "processing"
    completed = _job(TurnVideoAnalysisStatus.COMPLETED.value)
    completed.id = "completed"
    session = _StatusFilteringSession([queued, processing, completed])

    terminated = turn_video_queue.fail_pending_turn_video_jobs(session, 1, "interview_interrupted")

    assert terminated == 1
    assert queued.status == TurnVideoAnalysisStatus.FAILED.value
    assert queued.error == "interview_interrupted"
    # A processing native call and an already-completed result are left intact.
    assert processing.status == TurnVideoAnalysisStatus.PROCESSING.value
    assert completed.status == TurnVideoAnalysisStatus.COMPLETED.value
    assert session.committed
