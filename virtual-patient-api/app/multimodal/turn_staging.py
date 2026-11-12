"""Per-turn staging: each turn owns its immutable media; jobs read it directly.

Each student turn has
its own captured video file (``InterviewTurnMediaDB``); the durable
``TurnVideoAnalysisDB`` job points at that file through ``storage_key``, with no
a per-turn media window (no on-demand ffmpeg window cut). The patient turn is
text-to-speech and has no captured media.
"""
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

    Unlike the former block identity, there is no window: the media file IS the
    turn, so its ``sha256`` fully identifies the analysed content. Calibration is
    included so recalibrating a segment invalidates cached jobs.
    """
    payload = {"turn_media_id": media.id, "sha256": media.sha256,
               "metadata_hash": media.metadata_hash, "calibration": segment.calibration}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stage_turn_media(db, recording, validate_cache=False):
    """Derive turns and durable per-turn jobs from uploaded per-turn media.

    One ``InterviewTurnMediaDB`` row produces exactly one student turn. Patient
    turns are created from their conversation messages with TTS timing and never
    carry captured media, so they get no video job.
    """
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
        reliable = media.duration_ms is not None and media.encoded_timing.get("window_alignment") != "unavailable"
        start = media.session_clock_ms
        end = start + (media.duration_ms or 0)
        turn.start_ms, turn.end_ms = start, end
        turn.input_source = "camera_microphone" if media.speaker == "student" else "tts"
        turn.timing_source = "turn_media" if media.speaker == "student" else "tts_playback"
        turn.timing_quality = "measured" if reliable else "provisional"
        if not reliable:
            turn.start_ms = turn.end_ms = 0
            turn.timing_quality = "unavailable"
        db.flush()

        # Only student turns with reliable, non-empty media get a video job.
        if media.speaker != "student" or turn.timing_quality == "unavailable" or end <= start:
            continue
        identity = source_identity(media, segment)
        job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).first()
        existing = (job.result or {}) if job else {}
        previous = existing.get("turn_source")
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
        job.result = {"turn_source": {"turn_media_id": media.id, "identity": identity}}
        job.roi_snapshots = media.turn_metadata.get("interaction_area_snapshots", [])
        job.error = job.started_at = job.completed_at = None
        job.queued_at = datetime.now(timezone.utc)


def valid_turn_job(job, turn, segment):
    """A completed per-turn job is reusable while its media and runtime hold."""
    from app.multimodal.continuous_turns import runtime_identity

    data = (job.result or {}).get("extractor", {})
    source = (job.result or {}).get("turn_source")
    if job.status != "completed" or not source or data.get("turn_runtime") != runtime_identity():
        return False
    from sqlalchemy.orm import object_session
    media = object_session(job).get(InterviewTurnMediaDB, source["turn_media_id"])
    return bool(media and source["identity"] == source_identity(media, segment))


def extract_turn_paraverbal(media_path, turn, interview_id):
    """Run the isolated student-audio extractor over a turn's own media file.

    The media file is already scoped to one turn, so the subprocess analyses the
    whole clip (start 0 .. end duration) rather than a window inside a block.
    """
    from app.media.probe import probe_media_timing

    try:
        probe_media_timing(media_path, "a:0")
    except (ValueError, subprocess.SubprocessError):
        return None
    timing = probe_media_timing(media_path, "v:0")
    duration = int(timing.get("end_pts_ms") or 0)
    result = subprocess.run(
        [sys.executable, "-m", "app.multimodal.continuous_turns"],
        input=json.dumps({
            "path": str(media_path), "start": 0, "end": duration, "id": turn.id,
            "transcript": turn.transcript, "message_id": turn.message_id,
            "medical_interview_id": interview_id,
        }),
        text=True, capture_output=True, check=True, timeout=120,
    )
    return json.loads(result.stdout)
