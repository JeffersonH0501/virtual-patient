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
    if overrides.get("speaker", "student") == "student":
        base["speech_start_ms"] = 400
    base.update(overrides)
    return base


@pytest.mark.parametrize("playback_complete", [True, False])
def test_patient_capture_preserves_wait_and_only_stages_completed_playback(capture, tmp_path, playback_complete):
    state = capture
    with Session(state.engine) as db:
        message = InterviewMessageDB(interview_id=state.id, sender_type="patient", content="Synthetic reply")
        db.add(message)
        db.commit()
        message_id = message.id
        recording_id = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one().id
    from app.speech.preserved_audio import patient_audio_key
    audio = state.storage.root / patient_audio_key(state.id, recording_id, message_id)
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"preserved synthetic mp3")
    path = tmp_path / "camera.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=25:d=2",
        "-c:v", "libvpx", "-threads", "1", str(path)], check=True, timeout=20)
    metadata = _metadata(state, message_id=message_id, speaker="patient", session_clock_ms=2000,
                         playback_start_ms=700, playback_end_ms=1700, playback_complete=playback_complete)
    endpoint = state.root + f"/turns/{uuid4()}/video"
    response = state.client.put(endpoint, data={"metadata": json.dumps(metadata)},
        files={"video": ("camera.webm", path.read_bytes(), "video/webm")})
    assert response.status_code == 200, response.text
    manifest = state.client.get(state.root + "/turns").json()
    assert manifest["duration_ms"] == 4000
    entry = manifest["turns"][0]
    assert entry["metadata"]["playback_start_ms"] == 700
    assert manifest["replay"] == {"status": "unavailable"}
    with Session(state.engine) as db:
        turn = db.query(InterviewTurnDB).filter_by(message_id=message_id).one()
        job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).one_or_none()
        if playback_complete:
            assert (turn.start_ms, turn.end_ms) == (2700, 3700)
            assert job.result["turn_source"]["clip_start_ms"] == 700
        else:
            assert turn.timing_quality == "unavailable"
            assert job is None
            # Not analysable, but replay still seeks to where the reply is heard.
            assert (turn.start_ms, turn.end_ms) == (2700, 3700)


def test_patient_capture_rejects_microphone_track(capture, tmp_path):
    metadata = _metadata(capture, speaker="patient", message_id=capture.greeting_id)
    endpoint = capture.root + f"/turns/{uuid4()}/video"
    response = capture.client.put(endpoint, data={"metadata": json.dumps(metadata)},
        files={"video": ("camera.webm", _student_media(tmp_path), "video/webm")})
    assert response.status_code == 422
    assert "must not contain an audio track" in response.text


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
        assert turn.start_ms == 400
        job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).one()
        assert job.storage_key is not None
        assert (job.result or {}).get("turn_source", {}).get("clip_start_ms") == 400
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
        assert recording.capture_config.get("replay_preview") == {"status": "queued", "progress": 0}
        from app.models.processing_job import InterviewProcessingJobDB
        assert {job.kind for job in db.query(InterviewProcessingJobDB).all()} >= {"replay_preview", "pipeline"}
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


def test_idle_clip_keeps_replay_time_without_a_turn_or_job(capture, tmp_path):
    state = capture
    original = _student_media(tmp_path)
    idle_id, student_id = str(uuid4()), str(uuid4())
    idle = _metadata(state, message_id=None, speech_start_ms=None)
    assert state.client.put(state.root + f"/turns/{idle_id}/video", data={"metadata": json.dumps(idle)},
        files={"video": ("turn.webm", original, "video/webm")}).status_code == 200
    assert state.client.put(state.root + f"/turns/{student_id}/video",
        data={"metadata": json.dumps(_metadata(state, order=1, session_clock_ms=2000))},
        files={"video": ("turn.webm", original, "video/webm")}).status_code == 200
    final = state.client.post(state.root + "/turns/finalize",
        json={"turn_media_ids": [idle_id, student_id], "missing_message_ids": []})
    assert final.status_code == 200, final.text
    assert final.json()["recording_status"] == "ready"
    assert final.json()["duration_ms"] >= 3900
    with Session(state.engine) as db:
        assert db.query(InterviewTurnDB).count() == 1
        assert db.query(TurnVideoAnalysisDB).count() == 1


@pytest.mark.parametrize("overrides", [
    {"message_id": None, "speech_start_ms": 100},
    {"speech_start_ms": 2000},
    {"speaker": "patient", "speech_start_ms": 100},
])
def test_speech_onset_must_belong_to_a_student_message(capture, tmp_path, overrides):
    state = capture
    response = state.client.put(state.root + f"/turns/{uuid4()}/video",
        data={"metadata": json.dumps(_metadata(state, **overrides))},
        files={"video": ("turn.webm", _student_media(tmp_path), "video/webm")})
    assert response.status_code == 422


def test_student_clip_without_onset_has_no_analysis_window(capture, tmp_path):
    state = capture
    assert state.client.put(state.root + f"/turns/{uuid4()}/video",
        data={"metadata": json.dumps(_metadata(state, speech_start_ms=None))},
        files={"video": ("turn.webm", _student_media(tmp_path), "video/webm")}).status_code == 200
    with Session(state.engine) as db:
        assert db.query(InterviewTurnDB).one().timing_quality == "unavailable"
        assert db.query(TurnVideoAnalysisDB).count() == 0


def test_upload_is_stored_as_a_verified_seekable_copy(capture, tmp_path):
    import hashlib
    state = capture
    path = tmp_path / "recorded.webm"
    # A cue-less, duration-less WebM like MediaRecorder writes (live muxing).
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libvpx", "-c:a", "libopus",
        "-threads", "1", "-live", "1", "-f", "webm", str(path)], check=True, timeout=20)
    original = path.read_bytes()
    turn_media_id = str(uuid4())
    response = state.client.put(state.root + f"/turns/{turn_media_id}/video",
        data={"metadata": json.dumps(_metadata(state))}, files={"video": ("turn.webm", original, "video/webm")})
    assert response.status_code == 200, response.text
    with Session(state.engine) as db:
        media = db.get(InterviewTurnMediaDB, turn_media_id)
        stored = state.storage.resolve(media.storage_key)
        assert media.upload_sha256 == hashlib.sha256(original).hexdigest()
        assert media.sha256 == hashlib.sha256(stored.read_bytes()).hexdigest() != media.upload_sha256
        assert media.encoded_timing["container"]["container"] == "remuxed_copy_v1"
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(stored)],
        check=True, capture_output=True, text=True)
    assert float(probe.stdout) > 1.9
    # A retried upload of the same bytes is recognised by the upload digest.
    retry = state.client.put(state.root + f"/turns/{turn_media_id}/video",
        data={"metadata": json.dumps(_metadata(state))}, files={"video": ("turn.webm", original, "video/webm")})
    assert retry.json() == response.json()


def test_unverifiable_original_is_kept_as_recorded(tmp_path):
    from app.media.remux import remux_for_replay
    path = tmp_path / "broken.webm"
    path.write_bytes(b"not a real encoded original")
    assert remux_for_replay(path)["container"] == "as_recorded"
    assert path.read_bytes() == b"not a real encoded original"


def test_opening_greeting_is_timed_for_replay_but_not_analysed(capture, tmp_path):
    state = capture
    with Session(state.engine) as db:
        greeting = db.get(InterviewMessageDB, state.greeting_id)
        greeting.message_metadata = {**(greeting.message_metadata or {}), "opening": True}
        db.commit()
    path = tmp_path / "camera.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=25:d=2",
        "-c:v", "libvpx", "-threads", "1", str(path)], check=True, timeout=20)
    metadata = _metadata(state, message_id=state.greeting_id, speaker="patient",
                         playback_start_ms=300, playback_end_ms=1700, playback_complete=True)
    response = state.client.put(state.root + f"/turns/{uuid4()}/video", data={"metadata": json.dumps(metadata)},
        files={"video": ("camera.webm", path.read_bytes(), "video/webm")})
    assert response.status_code == 200, response.text
    with Session(state.engine) as db:
        turn = db.query(InterviewTurnDB).filter_by(message_id=state.greeting_id).one()
        assert (turn.start_ms, turn.end_ms, turn.timing_quality) == (300, 1700, "measured")
        assert db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).count() == 0


def test_replay_preview_is_served_only_once_ready(capture):
    from app.media.replay_preview import preview_key
    state = capture
    assert state.client.get(state.root + "/replay").status_code == 404
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {**recording.capture_config, "replay_preview": {"status": "ready", "progress": 100}}
        target = state.storage.root / preview_key(state.id, recording.id)
        db.commit()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"synthetic mp4 bytes")
    manifest = state.client.get(state.root + "/turns").json()
    assert manifest["replay"]["source"].endswith("/recording/replay")
    served = state.client.get(manifest["replay"]["source"], headers={"Range": "bytes=0-8"})
    assert served.status_code == 206 and served.content == b"synthetic"
