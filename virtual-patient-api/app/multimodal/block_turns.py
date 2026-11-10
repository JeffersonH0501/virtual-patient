"""Analysis windows refer to the preserved original, never an uploaded derivative."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.orm import object_session
from app.models.medical_interview import InterviewMessageDB, InterviewRecordingSegmentDB, InterviewTurnDB, TurnVideoAnalysisDB
from app.models.recording_block import InterviewRecordingBlockDB
from app.media.probe import probe_media_timing


def ordered_blocks(db, recording_id):
    return db.query(InterviewRecordingBlockDB).join(InterviewRecordingSegmentDB,
        InterviewRecordingSegmentDB.id == InterviewRecordingBlockDB.capture_attempt_id).filter(
        InterviewRecordingBlockDB.recording_id == recording_id).order_by(
        InterviewRecordingSegmentDB.sequence, InterviewRecordingBlockDB.order).all()


def source_identity(block, segment, window):
    payload = {"block_id": block.id, "sha256": block.sha256, "metadata_hash": block.metadata_hash,
               "window": window, "calibration": segment.calibration}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stage_block_turns(db, recording, validate_cache=False):
    messages = db.query(InterviewMessageDB).filter_by(interview_id=recording.medical_interview_id).order_by(InterviewMessageDB.id).all()
    by_id = {item.id: (index, item) for index, item in enumerate(messages)}
    offset = 0
    for block in ordered_blocks(db, recording.id):
        data = block.block_metadata
        segment = db.get(InterviewRecordingSegmentDB, block.capture_attempt_id)
        for speaker, message_id, window in (("student", data.get("student_message_id"), data.get("student_speech")),
                ("patient", data["patient_message_id"], data.get("patient_playback"))):
            if message_id is None:
                continue
            sequence, message = by_id[message_id]
            turn = db.query(InterviewTurnDB).filter_by(medical_interview_id=recording.medical_interview_id, message_id=message_id).first()
            if turn is None:
                turn = InterviewTurnDB(id=str(uuid4()), medical_interview_id=recording.medical_interview_id,
                    message_id=message_id, speaker=speaker, sequence=sequence, transcript=message.content)
                db.add(turn)
            turn.segment_id = segment.id
            reliable = block.duration_ms is not None and block.encoded_timing.get('window_alignment') != 'unavailable'
            start = window["start_ms"] if window else (block.duration_ms or 0)
            end = window["end_ms"] if window else start
            turn.start_ms, turn.end_ms = offset + start, offset + end
            turn.input_source = "camera_microphone" if speaker == "student" else "tts"
            turn.timing_source = "block_speech" if speaker == "student" else ("tts_playback" if window else "tts_written")
            turn.timing_quality = "measured" if speaker == "student" or data.get("patient_playback_complete", True) else "provisional"
            if speaker == 'patient' and data.get('patient_playback_complete', True):
                message.message_metadata = {**(message.message_metadata or {}), 'playback_confirmed': True}
            if not reliable or (speaker == 'student' and not data.get('student_speech_complete', True)):
                turn.start_ms = turn.end_ms = 0
                turn.timing_quality = 'unavailable'
            db.flush()
            if turn.timing_quality == 'unavailable' or not reliable or not window or end <= start:
                continue
            source = {"block_id": block.id, "identity": source_identity(block, segment, window), "window": window}
            job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).first()
            existing = (job.result or {}) if job else {}
            previous = existing.get("block_source") or existing.get("extractor", {}).get("block_capture")
            if job and previous == source and (job.status in {"queued", "processing"} or
                    (job.status == 'completed' and (not validate_cache or valid_block_job(job, turn, segment)))):
                continue
            if job is None:
                job = TurnVideoAnalysisDB(id=str(uuid4()), medical_interview_id=recording.medical_interview_id,
                    recording_id=recording.id, turn_id=turn.id, speaker=speaker, content_type=block.content_type,
                    size_bytes=block.size_bytes, sha256=block.sha256, roi_snapshots=[])
                db.add(job)
            job.start_ms, job.end_ms = turn.start_ms, turn.end_ms
            job.storage_key = None
            job.status, job.result = "queued", {"block_source": source}
            job.error = job.started_at = job.completed_at = None
            job.queued_at = datetime.now(timezone.utc)
        offset += block.duration_ms or 0


def valid_block_job(job, turn, segment):
    from app.multimodal.continuous_turns import runtime_identity
    data = (job.result or {}).get("extractor", {})
    source = data.get("block_capture")
    if job.status != "completed" or not source or data.get("block_runtime") != runtime_identity():
        return False
    block = object_session(job).get(InterviewRecordingBlockDB, source["block_id"])
    return bool(block and source["identity"] == source_identity(block, segment, source["window"]))


def prepare_block_sources(storage, block, segment, turn, source, directory):
    start, end = source["window"]["start_ms"], source["window"]["end_ms"]
    if source_identity(block, segment, source["window"]) != source["identity"]:
        raise ValueError("Block source identity changed")
    path = storage.resolve(block.storage_key)
    with path.open('rb') as original:
        if hashlib.file_digest(original, 'sha256').hexdigest() != block.sha256:
            raise ValueError("Preserved original content changed")
    timing = probe_media_timing(path, 'v:0')
    if start < 0 or end <= start or end > timing['end_pts_ms'] + 150 or timing['max_gap_ms'] > 150:
        raise ValueError("Block does not cover the analysis window")
    clip_start = max(0, start - 1000)
    clip_end = min(end + 1000, timing['end_pts_ms'])
    output = directory / 'turn.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', f'{clip_start / 1000:.3f}', '-i', str(path),
        '-t', f'{(clip_end - clip_start) / 1000:.3f}', '-map', '0:v:0', '-an', '-c:v', 'libvpx',
        '-deadline', 'realtime', '-threads', '1', str(output)], check=True, capture_output=True, timeout=120)
    audio_raw = None
    if turn.speaker == 'student':
        try:
            probe_media_timing(path, 'a:0')
        except (ValueError, subprocess.SubprocessError):
            pass
        else:
            result = subprocess.run([sys.executable, '-m', 'app.multimodal.continuous_turns'],
                input=json.dumps({'path': str(path), 'start': start, 'end': end, 'id': turn.id, 'transcript': turn.transcript,
                                  'message_id': turn.message_id}),
                text=True, capture_output=True, check=True, timeout=120)
            audio_raw = json.loads(result.stdout)
    return output, audio_raw, start - clip_start, clip_end - clip_start, clip_start
