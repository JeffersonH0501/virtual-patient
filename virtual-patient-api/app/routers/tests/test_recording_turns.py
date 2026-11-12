"""Per-turn media upload, finalize, recap and durable job staging contract."""
import json
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.medical_interview import (
    InterviewMessageDB, InterviewRecordingDB, InterviewRecordingSegmentDB,
    InterviewTurnDB, MedicalInterviewDB, TurnVideoAnalysisDB,
)
from app.models.turn_media import InterviewTurnMediaDB
from app.routers.tests.test_recording_segments import capture as segment_capture
from app.routers.tests.test_lifecycle_integrity import lifecycle_api, exchange_agent  # noqa: F401


@pytest.fixture
def capture(segment_capture):
    """A started per-turn capture with its router mounted and one student message."""
    from app.routers import recording_turns
    state = segment_capture
    state.client.app.include_router(recording_turns.router)
    with Session(state.engine) as db:
        student = InterviewMessageDB(interview_id=state.id, sender_type="user", content="Synthetic speech")
        db.add(student)
        db.commit()
        state.student_id = student.id
    return state


def _student_media(tmp_path):
    path = tmp_path / "turn.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libvpx", "-c:a", "libopus",
        "-threads", "1", str(path)], check=True, timeout=20)
    return path.read_bytes()


def _metadata(state, **overrides):
    base = {"capture_attempt_id": state.segment_id, "order": 0, "duration_ms": 2000,
            "message_id": state.student_id, "speaker": "student", "session_clock_ms": 0,
            "interaction_area_snapshots": []}
    base.update(overrides)
    return base


def test_turn_upload_is_immutable_idempotent_and_fences_stale_capture(capture, tmp_path):
    state = capture
    original = _student_media(tmp_path)
    turn_media_id = str(uuid4())
    endpoint = state.root + f"/turns/{turn_media_id}/video"

    def upload(payload=None, data=original):
        return state.client.put(endpoint, data={"metadata": json.dumps(payload or _metadata(state))},
            files={"video": ("turn.webm", data, "video/webm")})

    first = upload()
    assert first.status_code == 200, first.text
    assert first.json()["duration_ms"] >= 1900
    assert "storage_key" not in first.json()
    # Idempotent: same media + metadata returns the same receipt.
    assert upload().json() == first.json()
    # Immutable: a different order for the same id conflicts.
    assert upload(_metadata(state, order=1)).status_code == 409
    # A student turn and its durable job are staged from the upload.
    with Session(state.engine) as db:
        turn = db.query(InterviewTurnDB).filter_by(message_id=state.student_id).one()
        assert turn.input_source == "camera_microphone"
        job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).one()
        assert job.storage_key is not None
        assert (job.result or {}).get("turn_source")
    # Stale capture segment is fenced.
    state.client.headers["X-Capture-Segment"] = str(uuid4())
    assert upload().status_code == 409


def test_turn_recap_lists_media_with_streamable_source(capture, tmp_path):
    state = capture
    original = _student_media(tmp_path)
    turn_media_id = str(uuid4())
    assert state.client.put(state.root + f"/turns/{turn_media_id}/video",
        data={"metadata": json.dumps(_metadata(state))},
        files={"video": ("turn.webm", original, "video/webm")}).status_code == 200
    manifest = state.client.get(state.root + "/turns")
    assert manifest.status_code == 200, manifest.text
    entry = manifest.json()["turns"][0]
    assert entry["session_clock_ms"] == 0
    media = state.client.get(entry["student_video_source"], headers={"Range": "bytes=0-15"})
    assert media.status_code == 206 and media.content == original[:16]


def test_finalize_manifest_is_immutable_and_stages_pipeline(capture, tmp_path):
    state = capture
    original = _student_media(tmp_path)
    turn_media_id = str(uuid4())
    assert state.client.put(state.root + f"/turns/{turn_media_id}/video",
        data={"metadata": json.dumps(_metadata(state))},
        files={"video": ("turn.webm", original, "video/webm")}).status_code == 200
    final = state.client.post(state.root + "/turns/finalize",
        json={"turn_media_ids": [turn_media_id], "missing_message_ids": []})
    assert final.status_code == 200, final.text
    assert final.json()["duration_ms"] >= 1900
    with Session(state.engine) as db:
        assert db.query(InterviewTurnMediaDB).count() == 1
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        assert recording.capture_config.get("observation_processing", {}).get("status") == "queued"
    # Re-finalizing with a different manifest is rejected.
    assert state.client.post(state.root + "/turns/finalize",
        json={"turn_media_ids": [], "missing_message_ids": []}).status_code == 409


def test_incomplete_original_keeps_media_without_a_video_job(capture, tmp_path):
    # A media file whose encoded clock cannot be probed stays preserved, but its
    # unreliable timing yields an unavailable turn and no durable video job.
    state = capture
    turn_media_id = str(uuid4())
    response = state.client.put(state.root + f"/turns/{turn_media_id}/video",
        data={"metadata": json.dumps(_metadata(state))},
        files={"video": ("turn.webm", b"not a real encoded original", "video/webm")})
    assert response.status_code == 200, response.text
    with Session(state.engine) as db:
        media = db.query(InterviewTurnMediaDB).one()
        assert media.encoded_timing.get("window_alignment") == "unavailable"
        turn = db.query(InterviewTurnDB).filter_by(message_id=state.student_id).one()
        assert turn.timing_quality == "unavailable"
        assert db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).count() == 0
