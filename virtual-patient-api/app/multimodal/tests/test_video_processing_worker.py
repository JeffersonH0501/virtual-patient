"""Scheduler tests for the single video-processing service."""

from __future__ import annotations

import itertools
from concurrent.futures import Future
from pathlib import Path
from queue import PriorityQueue
from threading import Thread
from time import perf_counter
from types import SimpleNamespace

import pytest

from app.models.medical_interview import TurnVideoAnalysisStatus
from app.multimodal import video_processing_worker as worker


@pytest.fixture(autouse=True)
def isolated_scheduler(monkeypatch):
    monkeypatch.setattr(worker, "_jobs", PriorityQueue())
    monkeypatch.setattr(worker, "_sequence", itertools.count())
    monkeypatch.setattr(worker, "_scheduled_turn_ids", set())


def _calibration(path: Path, request_id: str, mode: str = "gaze") -> worker.CalibrationJob:
    return worker.CalibrationJob(
        request_id=request_id,
        mode=mode,
        media_path=path,
        metadata={},
        future=Future(),
        queued_at=perf_counter(),
    )


def test_calibration_has_strict_priority_and_fifo_order(monkeypatch, tmp_path):
    events: list[str] = []
    instances = []

    class FakeNativeWorker:
        def __init__(self):
            instances.append(self)

        def process_calibration(self, request_id, mode, media_path, metadata):
            events.append(f"calibration:{request_id}")
            return {"passed": True}

        def process_job(self, job_id):
            events.append(f"turn:{job_id}")
            return "completed"

        def close(self):
            events.append("close")

    monkeypatch.setattr(worker, "_PersistentTurnVideoWorker", FakeNativeWorker)
    monkeypatch.setattr(worker, "_mark_job_failed", lambda *args: None)
    worker._scheduled_turn_ids.update({"turn-1", "turn-2"})
    worker._enqueue(worker.BACKGROUND_PRIORITY, "turn-1")
    worker._enqueue(worker.BACKGROUND_PRIORITY, "turn-2")
    gaze_path = tmp_path / "gaze.webm"
    camera_path = tmp_path / "camera.webm"
    gaze_path.write_bytes(b"gaze")
    camera_path.write_bytes(b"camera")
    gaze = _calibration(gaze_path, "gaze")
    camera = _calibration(camera_path, "camera", "camera")
    worker._enqueue(worker.INTERACTIVE_PRIORITY, gaze)
    worker._enqueue(worker.INTERACTIVE_PRIORITY, camera)
    worker._enqueue(99, None)

    thread = Thread(target=worker._processor_loop)
    thread.start()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert events == [
        "calibration:gaze",
        "calibration:camera",
        "turn:turn-1",
        "turn:turn-2",
        "close",
    ]
    assert len(instances) == 1
    assert gaze.future.result(timeout=0) == {"passed": True}
    assert camera.future.result(timeout=0) == {"passed": True}
    assert not gaze_path.exists()
    assert not camera_path.exists()


def test_native_failure_recreates_worker_for_next_job(monkeypatch):
    events: list[str] = []
    failed: list[tuple[str, str]] = []

    class FakeNativeWorker:
        instance_count = 0

        def __init__(self):
            self.instance = FakeNativeWorker.instance_count
            FakeNativeWorker.instance_count += 1

        def process_job(self, job_id):
            events.append(f"process:{self.instance}:{job_id}")
            if job_id == "turn-1":
                raise RuntimeError("native failure")
            return "completed"

        def close(self):
            events.append(f"close:{self.instance}")

    monkeypatch.setattr(worker, "_PersistentTurnVideoWorker", FakeNativeWorker)
    monkeypatch.setattr(
        worker,
        "_mark_job_failed",
        lambda job_id, error: failed.append((job_id, error)),
    )
    worker._scheduled_turn_ids.update({"turn-1", "turn-2"})
    worker._enqueue(worker.BACKGROUND_PRIORITY, "turn-1")
    worker._enqueue(worker.BACKGROUND_PRIORITY, "turn-2")
    worker._enqueue(99, None)

    thread = Thread(target=worker._processor_loop)
    thread.start()
    thread.join(timeout=2)

    assert events == [
        "process:0:turn-1",
        "close:0",
        "process:1:turn-2",
        "close:1",
    ]
    assert failed == [("turn-1", "native failure")]


def test_warmup_loads_models_before_the_first_calibration_job(monkeypatch, tmp_path):
    events: list[str] = []

    class FakeNativeWorker:
        def warmup(self, request_id):
            events.append(f"warmup:{request_id}")

        def process_calibration(self, request_id, mode, media_path, metadata):
            events.append(f"calibration:{request_id}")
            return {"passed": True}

        def close(self):
            events.append("close")

    monkeypatch.setattr(worker, "_PersistentTurnVideoWorker", FakeNativeWorker)
    warmup = worker.WarmupJob("startup", Future(), perf_counter())
    path = tmp_path / "gaze.webm"
    path.write_bytes(b"gaze")
    calibration = _calibration(path, "gaze")
    worker._enqueue(worker.INTERACTIVE_PRIORITY, warmup)
    worker._enqueue(worker.INTERACTIVE_PRIORITY, calibration)
    worker._enqueue(99, None)

    thread = Thread(target=worker._processor_loop)
    thread.start()
    thread.join(timeout=2)

    assert events == ["warmup:startup", "calibration:gaze", "close"]
    assert warmup.future.result(timeout=0) is None
    assert calibration.future.result(timeout=0) == {"passed": True}


def test_startup_requeues_abandoned_processing_jobs(monkeypatch):
    jobs = [
        SimpleNamespace(
            status=TurnVideoAnalysisStatus.QUEUED.value,
            started_at=None,
            completed_at=None,
            error=None,
        ),
        SimpleNamespace(
            status=TurnVideoAnalysisStatus.PROCESSING.value,
            started_at=object(),
            completed_at=None,
            error="interrupted",
        ),
    ]

    class FakeQuery:
        def filter(self, *args):
            return self

        def all(self):
            return jobs

    class FakeSession:
        committed = False

        def query(self, model):
            return FakeQuery()

        def commit(self):
            self.committed = True

        def close(self):
            return None

    session = FakeSession()
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)

    worker._recover_jobs()

    assert session.committed
    assert [job.status for job in jobs] == [
        TurnVideoAnalysisStatus.QUEUED.value,
        TurnVideoAnalysisStatus.QUEUED.value,
    ]
    assert jobs[1].started_at is None
    assert jobs[1].error is None
