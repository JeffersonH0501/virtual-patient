"""Authenticated capture, storage, and replay of synchronized interview media."""

from app.media.access import _current_media_user, _get_interview, _require_completed_for_replay, _require_owner, _require_replay_access, _stream_private_media

from app.core.review_access import can_read_assessments, require_assessments

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.controllers.interview_lifecycle import lock_row, require_capture_open
from app.controllers.recording_segments import require_active_segment
from app.models.medical_interview import InterviewRecordingSegmentDB
from app.media import LocalMediaStorage, get_media_storage
from app.media.patient_roi import validate_patient_roi as _validate_patient_roi
from app.media.upload_route import RecordingUploadRoute
from app.multimodal.processing_jobs import stage_processing_job
from app.models.medical_interview import InterviewRecapResponse, InterviewRecordingDB, InterviewTurnDB, MedicalInterviewDB, RecapTurn, RecordingStateResponse, RecordingStatus, SenderType, TurnVideoAnalysisDB, TurnVideoAnalysisStatus
from app.models.medical_interview.interview_message import InterviewMessageDB
from app.models.user import UserDB, UserRole
from app.models.calibration_capture import CalibrationCaptureDB
from app.media.retention import media_retention_deadline


router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"], route_class=RecordingUploadRoute)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


from app.core.config import settings
MEDIA_RETENTION_MONTHS = settings.media_retention_months

# Non-terminal observation_processing statuses reported by the multimodal
# pipeline (see app/multimodal/pipeline.py STATUS_*). While a run is in one of
# these states a new reprocess request must be rejected to avoid interleaved
# writes to the same per-turn columns.
_PENDING_OBSERVATION_STATUSES = frozenset({"queued", "processing"})
MEDIA_DURATION_TOLERANCE_MS = 500

ALLOWED_CONTENT_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
KNOWN_FAILURE_CODES = {
    "browser-capture-unsupported",
    "recording-codec-unsupported",
    "capture-start-failed",
    "recording-upload-failed",
    "temporary-storage-failed",
    "media-recorder-failed",
}


def _require_analysis_admin(interview: MedicalInterviewDB, user: UserDB) -> None:
    """Limit manual analysis operations to superusers with interview access."""
    if user.role != UserRole.SUPERUSER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser analysis access required")
    _require_replay_access(interview, user)


def _recording_response(recording: InterviewRecordingDB) -> RecordingStateResponse:
    return RecordingStateResponse(
        interview_id=recording.medical_interview_id,
        recording_id=recording.id,
        recording_status=RecordingStatus(recording.status),
        duration_ms=recording.duration_ms,
    )


@router.get("/{interview_id}/learning-moments")
def get_learning_moments(interview_id: int, user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db)):
    from app.multimodal.learning_moments import read_learning_moments
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    require_assessments(db, interview, user)
    _require_completed_for_replay(interview)
    return read_learning_moments(db, interview_id)


@router.post("/{interview_id}/learning-moments/regenerate", status_code=202)
def regenerate_learning_moments(interview_id: int, user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db)):
    from app.multimodal.learning_moments import queue_learning_moments, read_learning_moments, recording_for
    interview = _get_interview(db, interview_id)
    _require_analysis_admin(interview, user)
    _require_completed_for_replay(interview)
    recording = recording_for(db, interview_id, lock=True)
    capture = recording.capture_config or {} if recording else {}
    if any(capture.get(key, {}).get("status") in {"queued", "processing", "stale"} for key in ("observation_processing", "evaluation_processing")):
        raise HTTPException(status_code=409, detail="Wait for current observations and evaluation")
    try:
        queue_learning_moments(db, interview_id, force=True)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return read_learning_moments(db, interview_id)


def persist_turn(interview_id, message_id, payload, user, db, *, commit=True):
    db.info["capture_wait"] = True
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    message = db.query(InterviewMessageDB).filter(
        # Completed transcripts and timing windows are immutable.
        InterviewMessageDB.id == message_id,
        InterviewMessageDB.interview_id == interview_id,
    ).first()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview message not found")
    expected_speaker = (
        "student"
        if getattr(message.sender_type, "value", message.sender_type) == SenderType.USER.value
        else "patient"
    )
    if payload.speaker != expected_speaker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Turn speaker does not match the interview message",
        )
    if payload.end_ms < payload.start_ms:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Turn end must not precede its start")

    turn = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id,
        InterviewTurnDB.message_id == message_id,
    ).first()
    values = payload.model_dump()
    snapshots = values.pop("patient_roi_snapshots")
    if snapshots is not None:
        _validate_patient_roi(snapshots, payload.end_ms - payload.start_ms)
    roi_matches = snapshots is None
    if snapshots is not None and turn is not None and turn.segment_id:
        existing_segment = db.get(InterviewRecordingSegmentDB, turn.segment_id)
        roi_matches = ((existing_segment.capture_config or {}).get("_turn_roi") or {}).get(str(message_id)) == snapshots
    if turn is not None and roi_matches and all(getattr(turn, key) == value for key, value in values.items()):
        return _turn_response(turn)
    require_capture_open(interview)
    segment = require_active_segment(db, interview_id, payload.segment_id)
    if segment is not None:
        if payload.start_ms < segment.offset_ms:
            raise HTTPException(status_code=422, detail="Turn starts before its recording segment")
        if snapshots is not None:
            config = dict(segment.capture_config or {})
            turn_roi = dict(config.get("_turn_roi") or {})
            previous_roi = turn_roi.get(str(message_id))
            if previous_roi is not None and previous_roi != snapshots:
                raise HTTPException(409, "Confirmed turn ROI cannot be replaced")
            turn_roi[str(message_id)] = snapshots
            samples = {sample.get("timestampMs", sample.get("timestamp_ms")): sample
                       for sample in config.get("patientRoiSnapshots", [])}
            for sample in snapshots:
                local_time = sample.get("timestampMs", sample.get("timestamp_ms")) + payload.start_ms - segment.offset_ms
                samples[local_time] = {**sample, "timestampMs": local_time}
            segment.capture_config = {**config, "_turn_roi": turn_roi,
                "patientRoiSnapshots": [samples[key] for key in sorted(samples)]}
        pending_message = (segment.capture_config or {}).get("_pending_patient_message_id")
        original_segment = (message.message_metadata or {}).get("capture_segment_id")
        if ((original_segment is not None and original_segment != segment.id)
                or (turn is not None and turn.segment_id != segment.id)) and message_id != pending_message:
            raise HTTPException(status_code=409, detail="Message belongs to a previous recording segment")
    if turn is None:
        turn = InterviewTurnDB(
            medical_interview_id=interview_id,
            message_id=message_id,
            **values,
        )
        db.add(turn)
    else:
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.turn_id == turn.id).first()
        if job is not None and any(getattr(turn, key) != value for key, value in values.items()):
            raise HTTPException(status_code=409, detail="A turn with queued analysis cannot be changed")
        for key, value in values.items():
            setattr(turn, key, value)
    if commit:
        db.commit()
        db.refresh(turn)
    else:
        db.flush()
    return _turn_response(turn)


@router.get("/{interview_id}/recording/turn-video-analyses")
def list_turn_video_analyses(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Expose the durable per-turn queue lifecycle without returning media paths."""
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    require_assessments(db, interview, user)
    jobs = db.query(TurnVideoAnalysisDB).filter(
        TurnVideoAnalysisDB.medical_interview_id == interview_id
    ).order_by(TurnVideoAnalysisDB.queued_at).all()
    counts = {state.value: 0 for state in TurnVideoAnalysisStatus}
    items = []
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
        items.append({
            "turn_id": job.turn_id,
            "speaker": job.speaker,
            "start_ms": job.start_ms,
            "end_ms": job.end_ms,
            "status": job.status,
            "error": job.error,
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        })
    return {"counts": counts, "jobs": items}


@router.post("/{interview_id}/evaluation/matched-control")
async def generate_matched_control(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    if user.role != UserRole.SUPERUSER:
        raise HTTPException(status_code=403, detail="Superuser research access required")
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    if getattr(interview.status, "value", interview.status) != "completed":
        raise HTTPException(status_code=409, detail="Matched controls require a completed interview")
    from app.multimodal.matched_control import evaluate_matched_text_control
    from app.agents.evaluation_agent import EvaluationAgent
    from app.controllers.medical_interview_controller import MedicalInterviewController
    from app.utils.language import convert_language_code_to_name
    source = MedicalInterviewController(db)
    data = source.get_interview_evaluation_data(interview_id)
    agent = EvaluationAgent(target_language=convert_language_code_to_name(interview.user.preferred_language or "en"), patient_gender=interview.patient_gender)
    run_id, results = await evaluate_matched_text_control(db, interview_id, agent, source.format_messages_for_evaluation(data["messages"]))
    return {"run_id": run_id, "condition": "MATCHED_TEXT_CONTROL", "evaluation_results": results}


@router.get("/{interview_id}/evaluation/runs")
def read_evaluation_runs(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    from app.models.medical_interview.interview_evaluation import InterviewEvaluationRunDB
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    require_assessments(db, interview, user)
    runs = db.query(InterviewEvaluationRunDB).filter(
        InterviewEvaluationRunDB.medical_interview_id == interview_id,
    )
    if user.role != UserRole.SUPERUSER:
        runs = runs.filter(InterviewEvaluationRunDB.evaluation_condition == "TEXT_PLUS_MULTIMODAL")
    runs = runs.order_by(InterviewEvaluationRunDB.created_at, InterviewEvaluationRunDB.id).all()
    return [{"id": run.id, "condition": run.evaluation_condition,
             "created_at": run.created_at, "snapshot": run.snapshot} for run in runs]


@router.get("/{interview_id}/recap", response_model=InterviewRecapResponse)
def get_recap(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
    storage: LocalMediaStorage = Depends(get_media_storage),
):
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    _require_completed_for_replay(interview, allow_processing=True)
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    turns = _recap_turns(db, interview)
    visible = can_read_assessments(db, interview, user)
    if not visible or user.role != UserRole.SUPERUSER:
        for turn in turns:
            turn.paraverbal = None
            turn.nonverbal_features = None
    duration_ms = (recording.duration_ms if recording is not None and recording.status in {"ready", "partial"}
                   and recording.ended_at is not None else None)
    if duration_ms is None:
        duration_ms = max((turn.end_ms for turn in turns if turn.end_ms is not None), default=None)
    if recording is None:
        return InterviewRecapResponse(
            interview_id=interview_id,
            recording_status=RecordingStatus.UNAVAILABLE,
            duration_ms=duration_ms,
            observation_processing={"status": "unavailable"},
            turns=turns,
        )
    if (recording.capture_config or {}).get('mediaTransport') == 'reusable_blocks_v1':
        from app.routers.recording_blocks import list_blocks
        manifest = list_blocks(interview_id, user, db, storage)
        return InterviewRecapResponse(interview_id=interview_id, recording_status=recording.status,
            duration_ms=manifest['duration_ms'], blocks=manifest['blocks'], turns=turns,
            observation_processing=(recording.capture_config or {}).get('observation_processing', {}) if visible else {},
            evaluation_processing=(recording.capture_config or {}).get('evaluation_processing', {}) if visible else {})
    return InterviewRecapResponse(interview_id=interview_id, recording_status=RecordingStatus.UNAVAILABLE,
        duration_ms=duration_ms, turns=turns, observation_processing={'status': 'unavailable'},
        evaluation_processing=(recording.capture_config or {}).get('evaluation_processing', {}) if visible else {})


@router.post("/{interview_id}/recording/reprocess", response_model=RecordingStateResponse)
def reprocess_recording(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    return _queue_review_refresh(interview_id, user, db, observations=True)


@router.post("/{interview_id}/evaluation/regenerate", response_model=RecordingStateResponse)
def regenerate_evaluation(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    return _queue_review_refresh(interview_id, user, db, observations=False)


def _queue_review_refresh(interview_id, user, db, *, observations):
    """Queue evaluation, optionally preceded by fresh observation extraction."""
    interview = _get_interview(db, interview_id)
    _require_analysis_admin(interview, user)
    if getattr(interview.status, "value", interview.status) != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed interviews can be reprocessed",
        )
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).with_for_update().first()
    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview has no recording to reprocess",
        )
    # A run already in flight must not be duplicated: the pipeline overwrites the
    # same per-turn columns, so two concurrent runs could interleave writes.
    current = (recording.capture_config or {}).get("observation_processing", {})
    capture = recording.capture_config or {}
    if (
        current.get("status") in _PENDING_OBSERVATION_STATUSES
        or capture.get("evaluation_processing", {}).get("status") in _PENDING_OBSERVATION_STATUSES
        or capture.get("learning_moments", {}).get("status") in {"pending", "processing"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is already being regenerated",
        )

    # Re-seed the observable lifecycle before the pipeline picks it up, mirroring
    # the seed written at finalize so the vocabulary stays consistent.
    recording.capture_config = {
        **capture,
        "evaluation_processing": {"status": "queued"},
        **({"observation_processing": {"status": "queued", "stage": "queued"}} if observations else {}),
    }
    stage_processing_job(db, interview_id, "observations" if observations else "evaluation", {"recording_id": recording.id})
    db.commit()
    db.refresh(recording)
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s event=reprocess_requested",
        interview_id,
        recording.id,
    )
    return _recording_response(recording)


def _calibration_media_available(capture):
    expiration = min(capture.retention_expires_at, media_retention_deadline(capture.created_at, MEDIA_RETENTION_MONTHS))
    return expiration > datetime.now(timezone.utc)


@router.get("/{interview_id}/calibration/captures")
def get_calibration_captures(interview_id: int, user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db), storage: LocalMediaStorage = Depends(get_media_storage)):
    interview = _get_interview(db, interview_id)
    _require_analysis_admin(interview, user)
    calibration = (interview.interview_metadata or {}).get("calibration", {})
    selected = calibration.get("capture_ids", {})
    captures = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview_id).order_by(CalibrationCaptureDB.created_at).all()
    entries = []
    for capture in captures:
        available = _calibration_media_available(capture)
        if available:
            try:
                storage.resolve(capture.storage_key)
            except FileNotFoundError:
                available = False
        entries.append({"id": capture.id, "stage": capture.stage, "created_at": capture.created_at,
            "duration_ms": capture.duration_ms, "metadata": capture.capture_metadata, "result": capture.result,
            "used_for": [stage for stage, identifier in selected.items() if identifier == capture.id],
            "media_url": f"/medical-interviews/{interview_id}/calibration/captures/{capture.id}/video" if available else None,
            "retention_expires_at": min(capture.retention_expires_at, media_retention_deadline(capture.created_at, MEDIA_RETENTION_MONTHS))})
    return {"calibration": calibration or None, "captures": entries}


@router.get("/{interview_id}/calibration/captures/{capture_id}/video")
def stream_calibration_capture(interview_id: int, capture_id: str, request: Request,
    user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
    storage: LocalMediaStorage = Depends(get_media_storage)):
    interview = _get_interview(db, interview_id)
    _require_analysis_admin(interview, user)
    capture = db.query(CalibrationCaptureDB).filter_by(id=capture_id, medical_interview_id=interview_id).first()
    if capture is None:
        raise HTTPException(404, "Calibration capture not found")
    if not _calibration_media_available(capture):
        raise HTTPException(410, "Calibration media retention has expired")
    try:
        path = storage.resolve(capture.storage_key)
    except FileNotFoundError as error:
        raise HTTPException(404, "Calibration media unavailable") from error
    return _stream_private_media(storage, path, request, capture.content_type)


def _turn_response(turn: InterviewTurnDB) -> RecapTurn:
    return RecapTurn(
        turn_id=turn.id,
        message_id=turn.message_id,
        speaker=turn.speaker,
        start_ms=turn.start_ms if turn.timing_quality != 'unavailable' else None,
        end_ms=turn.end_ms if turn.timing_quality != 'unavailable' else None,
        transcript=turn.transcript,
        input_source=turn.input_source,
        timing_source=turn.timing_source,
        timing_quality=turn.timing_quality,
        # Return the stored per-turn observations as-is. Every row is written by
        # the current multimodal pipeline in the canonical layered shape
        # (``raw``/``processed``/``base_labels``/``integrated_labels``/
        # ``quality``/``versions``/``config_hash``/``status``/``reason``), so the
        # recap serves that single contract directly. ``_without_none`` only
        # drops unavailable optional measurements from the payload; a patient
        # turn's absent paraverbal layer stays ``None``.
        paraverbal=_without_none(turn.paraverbal),
        nonverbal_features=_without_none(turn.nonverbal_features),
    )


def _without_none(value: Any) -> Any:
    """Remove unavailable optional measurements from API observation payloads."""
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value if item is not None]
    return value


def _recap_turns(db: Session, interview: MedicalInterviewDB) -> list[RecapTurn]:
    turns = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview.id
    ).order_by(InterviewTurnDB.sequence).all()
    messages = db.query(InterviewMessageDB).filter(
        InterviewMessageDB.interview_id == interview.id
    ).order_by(InterviewMessageDB.created_at, InterviewMessageDB.id).all()
    turns_by_message_id = {
        turn.message_id: turn for turn in turns if turn.message_id is not None
    }
    result: list[RecapTurn] = []
    for message in messages:
        turn = turns_by_message_id.get(message.id)
        if turn is not None:
            result.append(_turn_response(turn))
            continue
        sender_type = getattr(message.sender_type, "value", message.sender_type)
        result.append(
            RecapTurn(
                turn_id=f"legacy-{message.id}",
                message_id=message.id,
                speaker="student" if sender_type == SenderType.USER.value else "patient",
                transcript=message.content,
                input_source="legacy_message",
                timing_source="unavailable",
                timing_quality="unavailable",
            )
        )
    result.extend(
        _turn_response(turn) for turn in turns if turn.message_id is None
    )
    return result
