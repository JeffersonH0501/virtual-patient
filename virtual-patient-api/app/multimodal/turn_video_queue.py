"""Single-consumer FIFO for durable per-turn nonverbal video jobs."""

from __future__ import annotations

import logging
import json
import os
import select
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, perf_counter

from app.core.database import SessionLocal
from app.media.storage import get_media_storage
from app.multimodal.constants import (
    CALIBRATION_VISUAL_JOB_TIMEOUT_SECONDS,
    NONVERBAL_GAZE_QUEUE_CAPACITY,
    TURN_VIDEO_JOB_TIMEOUT_SECONDS,
)
from app.models.medical_interview import (
    InterviewRecordingDB,
    MedicalInterviewDB,
    TurnVideoAnalysisDB,
    TurnVideoAnalysisStatus,
)
from app.utils.runtime_metrics import current_rss_mb, process_id

logger = logging.getLogger(__name__)
_RESULT_PREFIX = "__TURN_VIDEO_RESULT__ "


class PersistentTurnVideoResources:
    """Heavy models shared by consecutive jobs inside the isolated process."""

    def __init__(self) -> None:
        from app.nonverbal.ccdbhg import load_default_bundle

        started_at = perf_counter()
        self.tracker = create_tracker()
        load_default_bundle()
        logger.info(
            "performance_event component=turn_video operation=worker_warmup "
            "phase=complete duration_ms=%.3f worker_pid=%s worker_rss_mb=%s",
            (perf_counter() - started_at) * 1000,
            process_id(),
            current_rss_mb(),
        )

    def tracker_for(self, profile: dict | None, *, kalman_enabled: bool = True):
        from app.nonverbal.gaze import reset_tracker

        affine_matrix = profile.get("affine_matrix") if profile else None
        return reset_tracker(
            self.tracker,
            affine_matrix=affine_matrix,
            kalman_enabled=kalman_enabled,
        )


class _PersistentTurnVideoWorker:
    """Line-protocol client for the restartable isolated visual worker."""

    def __init__(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.multimodal.isolated_worker",
                "turn-video-server",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )

    def _request(self, payload: dict, request_id: str, timeout: float) -> dict:
        if self.process.poll() is not None:
            raise RuntimeError(
                f"Native analysis worker exited with code {self.process.returncode}"
            )
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Native analysis worker pipes are unavailable")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        deadline = monotonic() + timeout
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Native analysis worker exceeded {timeout:g} seconds"
                )
            readable, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not readable:
                raise TimeoutError(
                    f"Native analysis worker exceeded {timeout:g} seconds"
                )
            line = self.process.stdout.readline()
            if not line:
                return_code = self.process.poll()
                raise RuntimeError(
                    f"Native analysis worker exited with code {return_code}"
                )
            if not line.startswith(_RESULT_PREFIX):
                logger.debug("turn_video_analysis result=worker_output_suppressed")
                continue
            result = json.loads(line[len(_RESULT_PREFIX):])
            if result.get("request_id") != request_id:
                raise RuntimeError("Native analysis worker returned a mismatched request ID")
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            return result

    def process_job(self, job_id: str) -> str:
        result = self._request(
            {"command": "turn-video", "request_id": job_id, "job_id": job_id},
            job_id,
            TURN_VIDEO_JOB_TIMEOUT_SECONDS,
        )
        return str(result.get("status", "failed"))

    def warmup(self, request_id: str) -> None:
        """Wait until the isolated process has loaded every visual model."""
        self._request(
            {"command": "warmup", "request_id": request_id},
            request_id,
            CALIBRATION_VISUAL_JOB_TIMEOUT_SECONDS,
        )

    def process_calibration(
        self,
        request_id: str,
        stage: str,
        media_path: Path,
        metadata: dict,
    ) -> dict:
        result = self._request(
            {
                "command": "calibration-visual",
                "request_id": request_id,
                "stage": stage,
                "media_path": str(media_path),
                "metadata": metadata,
            },
            request_id,
            CALIBRATION_VISUAL_JOB_TIMEOUT_SECONDS,
        )
        payload = result.get("result")
        if not isinstance(payload, dict):
            raise RuntimeError("Native analysis worker returned an invalid calibration result")
        return payload

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            if self.process.stdin is not None:
                self.process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                self.process.stdin.flush()
            self.process.wait(timeout=10)
        except Exception:  # noqa: BLE001 - force cleanup after native failures.
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def read_calibration_profile(interview):
    from app.multimodal.calibration import read_calibration_profile as implementation
    return implementation(interview)


def create_tracker(**kwargs):
    from app.nonverbal.gaze import create_tracker as implementation
    return implementation(**kwargs)


def extract_nonverbal_video_observations_parallel(*args, **kwargs):
    from app.nonverbal.video_observations import (
        extract_nonverbal_video_observations_parallel as implementation,
    )
    return implementation(*args, **kwargs)


def analyze_nods(observations):
    from app.nonverbal.ccdbhg import analyze_nods as implementation
    return implementation(observations)


def build_turn_raw_features(*args, **kwargs):
    from app.nonverbal.video_observations import build_turn_raw_features as implementation
    return implementation(*args, **kwargs)


def _mark_job_failed(job_id: str, error: str) -> None:
    """Persist a native child-process failure without risking the API worker."""
    db = SessionLocal()
    try:
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.id == job_id).first()
        if job is None or job.status == TurnVideoAnalysisStatus.COMPLETED.value:
            return
        job.status = TurnVideoAnalysisStatus.FAILED.value
        job.error = error[:2000]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _process_job(
    job_id: str,
    *,
    resources: PersistentTurnVideoResources | None = None,
) -> str:
    # These imports load PyTorch, TensorFlow and MediaPipe. This function runs
    # only in the isolated child process, so the long-lived API stays light.
    from app.nonverbal.ccdbhg import NodAnalysis
    from app.nonverbal.video_observations import TurnWindow

    processing_started = perf_counter()
    phase_started = processing_started
    timings_ms: dict[str, float] = {}
    db = SessionLocal()
    storage = get_media_storage()
    storage_key: str | None = None
    try:
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.id == job_id).first()
        if job is None or job.status == TurnVideoAnalysisStatus.COMPLETED.value:
            return "skipped"
        if job.status not in {
            TurnVideoAnalysisStatus.QUEUED.value,
            TurnVideoAnalysisStatus.PROCESSING.value,
        }:
            return "skipped"
        job.status = TurnVideoAnalysisStatus.PROCESSING.value
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        db.commit()
        timings_ms["job_claim"] = (perf_counter() - phase_started) * 1000
        storage_key = job.storage_key
        if not storage_key:
            raise FileNotFoundError("Turn video segment is unavailable")

        interview = db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == job.medical_interview_id,
        ).first()
        phase_started = perf_counter()
        profile = read_calibration_profile(interview)
        tracker = (
            resources.tracker_for(profile)
            if resources is not None
            else create_tracker(affine_matrix=profile.get("affine_matrix"))
            if profile
            else create_tracker()
        )
        timings_ms["model_setup"] = (perf_counter() - phase_started) * 1000
        phase_started = perf_counter()
        observations = extract_nonverbal_video_observations_parallel(
            storage.resolve(storage_key),
            tracker=tracker,
            queue_capacity=NONVERBAL_GAZE_QUEUE_CAPACITY,
        )
        timings_ms["video_and_gaze_extraction"] = (perf_counter() - phase_started) * 1000
        phase_started = perf_counter()
        try:
            nod_analysis = analyze_nods([item.shared for item in observations])
        except Exception:  # noqa: BLE001 - preserve gaze and smile for this turn.
            logger.exception("turn_video_analysis job_id=%s branch=ccdbhg result=failed", job_id)
            nod_analysis = NodAnalysis((), False, "extractor_failure")
        timings_ms["nod_analysis"] = (perf_counter() - phase_started) * 1000

        roi = list(job.roi_snapshots or [])
        duration_ms = max(1, job.end_ms - job.start_ms)
        window = TurnWindow(job.turn_id, 0, duration_ms, job.speaker)
        phase_started = perf_counter()
        raw = build_turn_raw_features(
            observations,
            window,
            nod_analysis=nod_analysis,
            calibration_profile=profile,
            patient_roi_snapshots=roi,
        )
        timings_ms["feature_assembly"] = (perf_counter() - phase_started) * 1000
        phase_started = perf_counter()
        job.result = raw.model_dump(mode="json")
        job.status = TurnVideoAnalysisStatus.COMPLETED.value
        job.completed_at = datetime.now(timezone.utc)
        job.storage_key = None
        db.commit()
        timings_ms["persistence"] = (perf_counter() - phase_started) * 1000
        try:
            storage.delete(storage_key)
        except Exception:  # noqa: BLE001 - persisted analysis remains valid.
            logger.exception(
                "turn_video_analysis job_id=%s result=cleanup_failed storage_key=%s",
                job.id, storage_key,
            )
        queue_wait_ms = (
            (job.started_at - job.queued_at).total_seconds() * 1000
            if job.started_at and job.queued_at else None
        )
        logger.info(
            "performance_event component=turn_video operation=analysis phase=complete "
            "job_id=%s turn_id=%s interview_id=%s queue_wait_ms=%s processing_ms=%.3f "
            "segment_duration_ms=%s sampled_frames=%s timings_ms=%s worker_pid=%s worker_rss_mb=%s",
            job.id, job.turn_id, job.medical_interview_id, queue_wait_ms,
            (perf_counter() - processing_started) * 1000, duration_ms, len(observations),
            json.dumps(timings_ms, sort_keys=True), process_id(), current_rss_mb(),
        )
        return "completed"
    except Exception as error:  # noqa: BLE001 - failure is durable and later turns continue.
        db.rollback()
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.id == job_id).first()
        if job is not None:
            job.status = TurnVideoAnalysisStatus.FAILED.value
            job.error = str(error)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.exception(
            "performance_event component=turn_video operation=analysis phase=failed "
            "job_id=%s processing_ms=%.3f timings_ms=%s worker_pid=%s worker_rss_mb=%s",
            job_id, (perf_counter() - processing_started) * 1000,
            json.dumps(timings_ms, sort_keys=True), process_id(), current_rss_mb(),
        )
        return "failed"
    finally:
        db.close()


def queue_depth() -> int:
    db = SessionLocal()
    try:
        return db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.status == TurnVideoAnalysisStatus.QUEUED.value,
        ).count()
    finally:
        db.close()


def fail_pending_turn_video_jobs(db, interview_id: int, reason: str) -> int:
    """Make queued jobs terminal; an already-processing native call may finish safely."""
    storage = get_media_storage()
    jobs = db.query(TurnVideoAnalysisDB).filter(
        TurnVideoAnalysisDB.medical_interview_id == interview_id,
        TurnVideoAnalysisDB.status == TurnVideoAnalysisStatus.QUEUED.value,
    ).all()
    for job in jobs:
        if job.storage_key:
            try:
                storage.delete(job.storage_key)
            except Exception:  # noqa: BLE001 - status transition must still persist.
                logger.exception("turn_video_analysis job_id=%s result=cancel_cleanup_failed", job.id)
        job.storage_key = None
        job.status = TurnVideoAnalysisStatus.FAILED.value
        job.error = reason
        job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return len(jobs)
