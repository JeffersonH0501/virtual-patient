"""Stage analysis against immutable per-turn media and verified playback windows."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

from app.models.medical_interview import (
    InterviewMessageDB, InterviewRecordingSegmentDB, InterviewTurnDB, TurnVideoAnalysisDB,
)
from app.models.turn_media import InterviewTurnMediaDB


def ordered_turn_media(db, recording_id):
    """All per-turn media for a recording, in global session-clock order."""
    return db.query(InterviewTurnMediaDB).join(
        InterviewRecordingSegmentDB,
        InterviewRecordingSegmentDB.id == InterviewTurnMediaDB.capture_attempt_id,
    ).filter(
        InterviewTurnMediaDB.recording_id == recording_id,
    ).order_by(
        InterviewRecordingSegmentDB.sequence, InterviewTurnMediaDB.order,
    ).all()


def source_identity(media, segment):
    """Cache key for a per-turn job: its media content plus its calibration.

    The metadata hash covers playback bounds, and calibration is included so
    recalibrating a segment invalidates cached jobs.
    """
    payload = {"turn_media_id": media.id, "sha256": media.sha256,
               "metadata_hash": media.metadata_hash, "calibration": segment.calibration}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def is_opening_message(message):
    """The patient's greeting starts the clock but precedes any student behavior to analyse."""
    return bool((message.message_metadata or {}).get("opening"))


def opening_message_ids(db, interview_id):
    messages = db.query(InterviewMessageDB).filter(InterviewMessageDB.interview_id == interview_id).all()
    return {message.id for message in messages if is_opening_message(message)}


def turn_media_window(media):
    """Return the analyzable interval relative to the immutable clip."""
    duration = media.duration_ms
    if not duration or media.encoded_timing.get("window_alignment") == "unavailable":
        return None
    metadata = media.turn_metadata
    if media.speaker == "student":
        # The clip opens when the floor returns to the student; analysis starts at the speech onset.
        start = metadata.get("speech_start_ms")
        return (start, duration) if start is not None and 0 <= start < duration else None
    start, end = metadata.get("playback_start_ms"), metadata.get("playback_end_ms")
    if metadata.get("playback_complete") and start is not None and end is not None and 0 <= start < end <= duration:
        return start, end
    return None


def stage_turn_media(db, recording, validate_cache=False):
    """Bind media to conversation turns and enqueue analyzable windows."""
    messages = db.query(InterviewMessageDB).filter_by(
        interview_id=recording.medical_interview_id,
    ).order_by(InterviewMessageDB.id).all()
    by_id = {item.id: (index, item) for index, item in enumerate(messages)}

    for media in ordered_turn_media(db, recording.id):
        if media.message_id is None:
            continue
        segment = db.get(InterviewRecordingSegmentDB, media.capture_attempt_id)
        sequence, message = by_id[media.message_id]
        turn = db.query(InterviewTurnDB).filter_by(
            medical_interview_id=recording.medical_interview_id, message_id=media.message_id,
        ).first()
        if turn is None:
            turn = InterviewTurnDB(
                id=str(uuid4()), medical_interview_id=recording.medical_interview_id,
                message_id=media.message_id, speaker=media.speaker, sequence=sequence,
                transcript=message.content,
            )
            db.add(turn)
        turn.segment_id = segment.id
        window = turn_media_window(media)
        turn.input_source = "camera_microphone" if media.speaker == "student" else "tts"
        turn.timing_source = "turn_media" if media.speaker == "student" else "tts_playback"
        if window is None:
            # Not analysable, but the transcript still seeks to where the turn is heard.
            metadata = media.turn_metadata
            start = metadata.get("playback_start_ms") if media.speaker == "patient" else metadata.get("speech_start_ms")
            start = start if isinstance(start, int) and start >= 0 else 0
            end = metadata.get("playback_end_ms") if media.speaker == "patient" else None
            turn.start_ms = media.session_clock_ms + start
            turn.end_ms = media.session_clock_ms + (end if isinstance(end, int) and end > start else start)
            turn.timing_quality = "unavailable"
            continue
        start, end = window
        turn.start_ms = media.session_clock_ms + start
        turn.end_ms = media.session_clock_ms + end
        turn.timing_quality = "measured"
        if is_opening_message(message):
            continue
        db.flush()
        identity = source_identity(media, segment)
        job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).first()
        existing = (job.result or {}) if job else {}
        previous = existing.get("turn_source") or existing.get("extractor", {}).get("turn_source")
        if job and previous and previous.get("identity") == identity and (
            job.status in {"queued", "processing"}
            or (job.status == "completed" and (not validate_cache or valid_turn_job(job, turn, segment)))
        ):
            continue
        if job is None:
            job = TurnVideoAnalysisDB(
                id=str(uuid4()), medical_interview_id=recording.medical_interview_id,
                recording_id=recording.id, turn_id=turn.id, speaker=media.speaker,
                content_type=media.content_type, size_bytes=media.size_bytes, sha256=media.sha256,
                roi_snapshots=[],
            )
            db.add(job)
        job.start_ms, job.end_ms = turn.start_ms, turn.end_ms
        job.storage_key = media.storage_key
        job.content_type, job.size_bytes, job.sha256 = media.content_type, media.size_bytes, media.sha256
        job.status = "queued"
        job.result = {"turn_source": {"turn_media_id": media.id, "identity": identity,
                                      "clip_start_ms": start, "clip_duration_ms": media.duration_ms}}
        job.roi_snapshots = media.turn_metadata.get("interaction_area_snapshots", [])
        job.error = job.started_at = job.completed_at = None
        job.queued_at = datetime.now(timezone.utc)


def valid_turn_job(job, turn, segment):
    """A completed per-turn job is reusable while its media and runtime hold."""
    from app.multimodal.continuous_turns import runtime_identity

    data = (job.result or {}).get("extractor", {})
    source = data.get("turn_source")
    if job.status != "completed" or not source or data.get("turn_runtime") != runtime_identity():
        return False
    from sqlalchemy.orm import object_session
    media = object_session(job).get(InterviewTurnMediaDB, source["turn_media_id"])
    return bool(media and turn_media_window(media) is not None and source["identity"] == source_identity(media, segment))


def extract_turn_paraverbal(media_path, turn, interview_id, start_ms, end_ms):
    """Run the isolated student-audio extractor over the speech window of a turn's clip.

    Returns ``None`` silently for any subprocess, encoding, or timeout failure so
    that a bad audio stream never causes the nonverbal job to fail.
    """
    from app.media.probe import probe_media_timing

    try:
        # A single call without a stream filter returns timing for all streams;
        # if the file has no audio track it raises ValueError from probe_media_timing.
        try:
            probe_media_timing(media_path, "a:0")
        except (ValueError, subprocess.SubprocessError):
            return None
        result = subprocess.run(
            [sys.executable, "-m", "app.multimodal.continuous_turns"],
            input=json.dumps({
                "path": str(media_path), "start": start_ms, "end": end_ms, "id": turn.id,
                "transcript": turn.transcript, "message_id": turn.message_id,
                "medical_interview_id": interview_id,
            }),
            text=True, capture_output=True, check=True, timeout=120,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, OSError, ValueError):
        return None
