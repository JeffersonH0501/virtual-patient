"""Immutable originals and encoded local windows for reusable interview blocks."""
import json
import subprocess
from uuid import uuid4

from sqlalchemy.orm import Session
from unittest.mock import Mock
import pytest
from app.models.medical_interview import InterviewRecordingDB

from app.routers.tests.test_recording_segments import capture as legacy_capture
from app.routers.tests.test_lifecycle_integrity import lifecycle_api, exchange_agent


@pytest.fixture
def capture(legacy_capture):
    from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingSegmentDB
    state = legacy_capture
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'recording_transport': 'reusable_blocks_v1'}
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {'mediaTransport': 'reusable_blocks_v1'}
        segment = db.get(InterviewRecordingSegmentDB, state.segment_id)
        segment.capture_config = {**segment.capture_config, 'mediaTransport': 'reusable_blocks_v1'}
        db.commit()
    return state


def finalized_block(state):
    from app.routers import recording_blocks
    state.client.app.include_router(recording_blocks.router)
    block_id = str(uuid4())
    metadata = {"capture_attempt_id": state.segment_id, "order": 0, "duration_ms": 1000,
                "patient_message_id": state.greeting_id, "patient_audio_missing": True}
    response = state.client.put(state.root + f"/blocks/{block_id}", data={"metadata": json.dumps(metadata)},
        files={"file": ("synthetic.webm", b"incomplete synthetic original", "video/webm")})
    assert response.status_code == 200, response.text
    response = state.client.post(state.root + "/blocks/finalize", json={"block_ids": [block_id]})
    assert response.status_code == 200, response.text
    return block_id


def test_finalized_capture_exposes_safe_continuation_after_reload(capture):
    state = capture
    finalized_block(state)
    detail = state.client.get(f"/medical-interviews/{state.id}/complete").json()
    assert detail["lifecycle"]["phase"] == "capture_finalized"
    assert detail["lifecycle"]["can_complete"] is True
    assert detail["lifecycle"]["can_resume_capture"] is False
    state.client.headers.pop("X-Capture-Segment")
    response = state.client.post(f"/medical-interviews/{state.id}/complete")
    assert response.status_code == 200, response.text
    assert response.json()["interview"]["status"] == "processing"
    assert state.client.post(f"/medical-interviews/{state.id}/complete").status_code == 200


def test_failed_completion_exposes_owner_recovery_without_assessments(capture):
    from app.models.medical_interview import MedicalInterviewDB
    state = capture
    finalized_block(state)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = "interrupted"
        interview.interview_metadata = {**interview.interview_metadata,
            "completion_processing": {"status": "failed", "error_code": "completion-processing-failed"}}
        db.commit()
    response = state.client.get(f"/medical-interviews/{state.id}/complete")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["lifecycle"]["can_retry_completion"] is True
    assert detail["lifecycle"]["phase"] == "completion_failed"
    assert detail["lifecycle"]["recording_transport"] == "reusable_blocks_v1"
    assert detail["interview_evaluation"] is None
    assert detail["multimodal_interview_evaluation"] is None
    assert detail["review_access"]["can_view_assessments"] is False


@pytest.mark.parametrize("damaged", [False, True])
def test_completion_retry_uses_failed_block_original(capture, damaged):
    from app.models.medical_interview import MedicalInterviewDB, InterviewTurnDB, TurnVideoAnalysisDB, InterviewRecordingSegmentDB
    from app.models.recording_block import InterviewRecordingBlockDB
    from app.multimodal.block_turns import source_identity
    state = capture
    block_id = finalized_block(state)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = "interrupted"
        interview.interview_metadata = {**interview.interview_metadata, "completion_processing": {"status": "failed"}}
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {**recording.capture_config, "observation_processing": {"status": "failed"}}
        turn = db.query(InterviewTurnDB).filter_by(medical_interview_id=state.id).one()
        block = db.get(InterviewRecordingBlockDB, block_id)
        segment = db.get(InterviewRecordingSegmentDB, state.segment_id)
        window = {"start_ms": 0, "end_ms": 1000}
        db.add(TurnVideoAnalysisDB(recording_id=recording.id, medical_interview_id=state.id, turn_id=turn.id,
            speaker="patient", start_ms=0, end_ms=1000, storage_key=None, content_type="video/webm",
            size_bytes=1, sha256="a" * 64, status="failed",
            result={"block_source": {"block_id": block_id, "window": window,
                "identity": source_identity(block, segment, window)}}))
        db.commit()
        if damaged:
            state.storage.resolve(block.storage_key).write_bytes(b"changed synthetic original")
    response = state.client.post(f"/medical-interviews/{state.id}/complete")
    assert response.status_code == (409 if damaged else 200), response.text
    with Session(state.engine) as db:
        assert db.query(TurnVideoAnalysisDB).one().status == ("failed" if damaged else "queued")


def test_block_start_rejects_geometry_outside_its_calibration(lifecycle_api):
    from app.routers import recording_segments
    from app.models.medical_interview import MedicalInterviewDB
    state = lifecycle_api
    state.client.app.include_router(recording_segments.router)
    geometry = {"viewport_width": 1000, "viewport_height": 700, "video_width": 640, "video_height": 480}
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        calibration = interview.interview_metadata["calibration"]
        calibration["profile"]["capture_geometry"] = geometry
        interview.interview_metadata = {"calibration": calibration, "recording_transport": "reusable_blocks_v1"}
        db.commit()
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    request_id = str(uuid4())
    url = f"/medical-interviews/{state.id}/recording/segments"
    payload = {"request_id": request_id, "capture_config": {"mediaTransport": "reusable_blocks_v1", "geometry": {**geometry, "viewport_width": 999}}}
    assert state.client.post(url, json=payload).status_code == 409
    payload["capture_config"]["geometry"] = geometry
    assert state.client.post(url, json=payload).status_code == 200


def test_recovery_messages_can_page_beyond_first_hundred(capture):
    from app.models.medical_interview import InterviewMessageDB
    state = capture
    with Session(state.engine) as db:
        for index in range(104):
            db.add(InterviewMessageDB(interview_id=state.id, sender_type="user", content=f"Synthetic {index}"))
        db.commit()
    response = state.client.get(f"/medical-interviews/{state.id}/messages?offset=100")
    assert response.status_code == 200, response.text
    assert len(response.json()["messages"]) == 5
    assert response.json()["messages"][-1]["content"] == "Synthetic 103"


def test_block_upload_is_immutable_and_fences_stale_capture(capture, tmp_path):
    from app.routers import recording_blocks
    state = capture
    state.client.app.include_router(recording_blocks.router)
    path = tmp_path / "block.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "color=c=black:s=64x64:r=10:d=2", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=2", "-c:v", "libvpx", "-c:a", "libopus",
        "-threads", "1", str(path)], check=True, timeout=20)
    original = path.read_bytes()
    block_id = str(uuid4())
    endpoint = state.root + f"/blocks/{block_id}"
    metadata = {"capture_attempt_id": state.segment_id, "order": 0,
        "duration_ms": 2000, "patient_message_id": state.greeting_id,
        "patient_playback": {"start_ms": 500, "end_ms": 1800},
        "student_message_id": None, "student_speech": None,
        "patient_audio_missing": True, "recovery": False}
    def upload(payload=metadata, data=original):
        return state.client.put(endpoint, data={"metadata": json.dumps(payload)},
            files={"file": ("block.webm", data, "video/webm")})
    first = upload()
    assert first.status_code == 200, first.text
    assert first.json()["duration_ms"] >= 1900
    assert "storage_key" not in first.json()
    assert upload().json() == first.json()
    assert upload({**metadata, "order": 1}).status_code == 409
    assert upload({**metadata, "patient_playback": {"start_ms": 0, "end_ms": 9000}}).status_code == 422
    manifest = state.client.get(state.root + "/blocks")
    assert manifest.status_code == 200, manifest.text
    entry = manifest.json()["blocks"][0]
    assert entry["offset_ms"] == 0
    assert entry["patient_audio_source"] is None
    media = state.client.get(entry["student_video_source"], headers={"Range": "bytes=0-15"})
    assert media.status_code == 206 and media.content == original[:16]
    final = state.client.post(state.root + '/blocks/finalize', json={"block_ids": [block_id], "missing_message_ids": []})
    assert final.status_code == 200, final.text
    assert final.json()['duration_ms'] == first.json()['duration_ms']
    from app.models.recording_block import InterviewRecordingBlockDB
    with Session(state.engine) as db:
        assert db.query(InterviewRecordingBlockDB).count() == 1
    state.client.headers["X-Capture-Segment"] = str(uuid4())
    assert upload().status_code == 409


def test_block_patient_playback_and_replay_use_one_preserved_original(capture, monkeypatch):
    from app.routers import speech
    from app.speech.contracts import SynthesizedAudio
    state = capture
    state.client.app.include_router(speech.router)
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {**(recording.capture_config or {}), "mediaTransport": "reusable_blocks_v1"}
        db.commit()
    generate = Mock(return_value=SynthesizedAudio(b"exact-original", "audio/mpeg", "synthetic", "test"))
    monkeypatch.setattr(speech.SpeechService, 'synthesize_patient_message', generate)
    monkeypatch.setattr(speech, 'get_media_storage', lambda: state.storage)
    endpoint = f"/medical-interviews/{state.id}/messages/{state.greeting_id}/speech"
    for method in (state.client.get, state.client.get, state.client.post):
        response = method(endpoint)
        assert response.status_code == 200, response.text
        assert response.content == b"exact-original"
    assert generate.call_count == 1


def test_incomplete_original_is_preserved_without_fabricated_duration_or_analysis(capture):
    from app.routers import recording_blocks
    from app.models.medical_interview import InterviewTurnDB, TurnVideoAnalysisDB
    state = capture
    state.client.app.include_router(recording_blocks.router)
    block_id = str(uuid4())
    payload = {'capture_attempt_id': state.segment_id, 'order': 0, 'duration_ms': 2000,
               'patient_message_id': state.greeting_id, 'patient_audio_missing': True}
    original = b'Synthetic incomplete encoded original'
    response = state.client.put(state.root + f'/blocks/{block_id}', data={'metadata': json.dumps(payload)},
        files={'file': ('incomplete.webm', original, 'video/webm')})
    assert response.status_code == 200, response.text
    assert response.json()['preserved'] is True and response.json()['duration_ms'] is None
    with Session(state.engine) as db:
        assert db.query(TurnVideoAnalysisDB).count() == 0
        assert db.query(InterviewTurnDB).one().timing_quality == 'unavailable'
    final = state.client.post(state.root + '/blocks/finalize', json={'block_ids': [block_id]})
    assert final.status_code == 200 and final.json()['duration_ms'] is None


def test_list_duration_matches_playback_for_incomplete_and_complete_blocks(capture):
    from app.controllers.medical_interview_controller import MedicalInterviewController
    from app.models.medical_interview import MedicalInterviewDB
    from app.models.recording_block import InterviewRecordingBlockDB
    from app.models.user import UserDB
    from app.routers.recording_blocks import list_blocks

    state = capture
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        for order, duration in enumerate((1200, None)):
            db.add(InterviewRecordingBlockDB(id=str(uuid4()), recording_id=recording.id,
                capture_attempt_id=state.segment_id, order=order, duration_ms=duration,
                storage_key=str(uuid4()), content_type='video/webm', size_bytes=1,
                sha256='0' * 64, metadata_hash='1' * 64, block_metadata={'patient_message_id': None}, encoded_timing={}))
        db.flush()
        controller = MedicalInterviewController(db)
        user = db.get(UserDB, interview.user_id)
        player_duration = list_blocks(interview.id, user, db, state.storage)['duration_ms']
        assert player_duration == 1200
        assert controller._recorded_duration(interview) == player_duration // 1000
        assert controller._recorded_durations([interview])[interview.id] == player_duration // 1000
        assert type(controller._recorded_durations([interview])[interview.id]) is int
        block = db.query(InterviewRecordingBlockDB).filter_by(recording_id=recording.id, order=1).one()
        block.duration_ms = 2300
        db.flush()
        player_duration = list_blocks(interview.id, user, db, state.storage)['duration_ms']
        assert player_duration == 3500
        assert controller._recorded_duration(interview) == player_duration // 1000
        assert controller._recorded_durations([interview])[interview.id] == player_duration // 1000


def test_postgres_block_sum_is_returned_as_an_integer():
    from decimal import Decimal
    from types import SimpleNamespace
    from app.controllers.medical_interview_controller import MedicalInterviewController

    class Query:
        def __init__(self, rows):
            self.rows = rows

        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        def all(self):
            return self.rows

    class Database:
        results = [[(1, None)], [(1, Decimal('123400'))]]

        def query(self, *args):
            return Query(self.results.pop(0))

    duration = MedicalInterviewController(Database())._recorded_duration(SimpleNamespace(id=1))
    assert type(duration) is int and duration == 123


def test_lost_database_acknowledgement_never_deletes_the_committed_original(capture, monkeypatch):
    from app.routers import recording_blocks
    from app.models.recording_block import InterviewRecordingBlockDB
    state = capture
    state.client.app.include_router(recording_blocks.router)
    block_id = str(uuid4())
    metadata = {'capture_attempt_id': state.segment_id, 'order': 0, 'duration_ms': 1000,
                'patient_message_id': state.greeting_id, 'patient_audio_missing': True}
    commit = Session.commit
    lost = False
    def lose_reply(db):
        nonlocal lost
        target = db.get(InterviewRecordingBlockDB, block_id) is not None
        commit(db)
        if target and not lost:
            lost = True
            raise ConnectionError('Synthetic lost commit acknowledgement')
    monkeypatch.setattr(Session, 'commit', lose_reply)
    def upload():
        return state.client.put(state.root + f'/blocks/{block_id}', data={'metadata': json.dumps(metadata)},
            files={'file': ('original.webm', b'Synthetic incomplete original', 'video/webm')})
    with pytest.raises(ConnectionError):
        upload()
    with Session(state.engine) as db:
        block = db.get(InterviewRecordingBlockDB, block_id)
        assert state.storage.resolve(block.storage_key).read_bytes() == b'Synthetic incomplete original'


    assert upload().status_code == 200
    with Session(state.engine) as db:
        block = db.get(InterviewRecordingBlockDB, block_id)
        state.storage.delete(block.storage_key)
    repaired = upload()
    assert repaired.status_code == 200, repaired.text
    with Session(state.engine) as db:
        block = db.get(InterviewRecordingBlockDB, block_id)
        assert state.storage.resolve(block.storage_key).read_bytes() == b'Synthetic incomplete original'


def test_completion_accepts_evidence_gaps_already_recorded_by_authorized_recovery(capture):
    from app.routers import recording_blocks
    from app.models.medical_interview import MedicalInterviewDB
    state = capture
    state.client.app.include_router(recording_blocks.router)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'missing_evidence_message_ids': [state.greeting_id]}
        db.commit()
    response = state.client.post(state.root + '/blocks/finalize', json={'block_ids': []})
    assert response.status_code == 200, response.text
    assert response.json() == {'duration_ms': None, 'recording_status': 'partial'}


def test_force_completion_without_any_active_recorder(lifecycle_api):
    from app.routers import recording_blocks, recording_segments
    from app.models.medical_interview import MedicalInterviewDB
    state = lifecycle_api
    state.client.app.include_router(recording_segments.router)
    state.client.app.include_router(recording_blocks.router)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'recording_transport': 'reusable_blocks_v1'}
        db.commit()
    assert state.client.post(f'/medical-interviews/{state.id}/start').status_code == 200
    root = f'/medical-interviews/{state.id}'
    response = state.client.post(root + '/recording/resume', json={'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    attempt = response.json()['resume_attempt_id']
    message_id = state.client.get(root + '/messages').json()['messages'][0]['id']
    gap = state.client.post(root + '/recording/blocks/recovery', json={'missing_message_ids': [message_id]}, headers={'X-Resume-Attempt': attempt})
    assert gap.status_code == 200, gap.text
    closed = state.client.post(root + '/abandon', headers={'X-Resume-Attempt': attempt})
    assert closed.status_code == 200, closed.text
    assert closed.json()['status'] == 'interrupted'
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        assert recording.status == 'partial' and recording.duration_ms is None


def test_old_tab_cannot_publish_but_authorized_resume_can_preserve_its_block(capture):
    from app.routers import recording_blocks
    state = capture
    state.client.app.include_router(recording_blocks.router)
    attempt = state.client.post(state.root + '/resume', json={'request_id': str(uuid4())}).json()['resume_attempt_id']
    metadata = {'capture_attempt_id': state.segment_id, 'order': 0, 'duration_ms': 1000,
                'patient_message_id': state.greeting_id, 'patient_audio_missing': True}
    endpoint = state.root + f'/blocks/{uuid4()}'
    def upload(headers=None):
        return state.client.put(endpoint, headers=headers, data={'metadata': json.dumps(metadata)},
            files={'file': ('original.webm', b'Synthetic recoverable original', 'video/webm')})
    assert upload().status_code == 409
    preserved = upload({'X-Resume-Attempt': attempt})
    assert preserved.status_code == 200, preserved.text
    assert upload().status_code == 409


def test_ten_interviews_preserve_independent_originals_and_finalize_without_analysis(lifecycle_api, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from time import perf_counter
    from types import SimpleNamespace
    from fastapi import Header
    from app.core.auth import get_current_active_user
    from app.routers import recording_blocks, recording_segments
    from app.routers.interview_recordings import _current_media_user
    from app.models.user import UserDB, UserRole
    from app.models.medical_interview import MedicalInterviewDB, InterviewStatus
    from app.models.recording_block import InterviewRecordingBlockDB
    from app.routers.tests.test_interview_calibration import calibration_payload
    state = lifecycle_api
    state.client.app.include_router(recording_segments.router)
    state.client.app.include_router(recording_blocks.router)
    actors, interviews = {}, []
    with Session(state.engine) as db:
        for index in range(10):
            user = UserDB(name='Synthetic block concurrency', email=uuid4().hex + '@example.org', hashed_password='unused',
                role=UserRole.STUDENT, organization_id=state.actor.organization_id)
            db.add(user); db.flush()
            interview = MedicalInterviewDB(user_id=user.id, clinical_case_id=state.case_id, status=InterviewStatus.IN_PROGRESS,
                interview_metadata={'calibration': calibration_payload(), 'recording_transport': 'reusable_blocks_v1'})
            db.add(interview); db.flush()
            actors[str(index)] = SimpleNamespace(id=user.id, role=UserRole.STUDENT, organization_id=state.actor.organization_id, preferred_language='en')
            interviews.append(interview.id)
        db.commit()
    def actor(x_test_actor: str = Header()):
        return actors[x_test_actor]
    state.client.app.dependency_overrides[get_current_active_user] = actor
    state.client.app.dependency_overrides[_current_media_user] = actor
    source = tmp_path / 'known-signals.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=64x64:r=10:d=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libvpx', '-c:a', 'libopus', '-threads', '1', str(source)], check=True, timeout=20)
    captures = []
    expected = {}
    for index, interview_id in enumerate(interviews):
        headers = {'X-Test-Actor': str(index)}
        assert state.client.post(f'/medical-interviews/{interview_id}/start', headers=headers).status_code == 200
        message_id = state.client.get(f'/medical-interviews/{interview_id}/messages', headers=headers).json()['messages'][0]['id']
        attempt = str(uuid4())
        started = state.client.post(f'/medical-interviews/{interview_id}/recording/segments', headers=headers,
            json={'request_id': attempt, 'capture_config': {'mediaTransport': 'reusable_blocks_v1', 'geometry': {'viewport_width': 1000, 'viewport_height': 700}}})
        assert started.status_code == 200, started.text
        unique = tmp_path / f'original-{interview_id}.webm'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-map', '0', '-c', 'copy',
            '-metadata', f'comment=synthetic-interview-{interview_id}', str(unique)], check=True, timeout=20)
        expected[interview_id] = unique.read_bytes()
        captures.append((interview_id, message_id, attempt, headers))
    def preserve(capture):
        interview_id, message_id, attempt, headers = capture
        block_id = str(uuid4())
        metadata = {'capture_attempt_id': attempt, 'order': 0, 'duration_ms': 2000, 'patient_message_id': message_id,
            'patient_playback': {'start_ms': 200, 'end_ms': 1800}, 'patient_audio_missing': True}
        started = perf_counter()
        response = state.client.put(f'/medical-interviews/{interview_id}/recording/blocks/{block_id}',
            headers={**headers, 'X-Capture-Segment': attempt}, data={'metadata': json.dumps(metadata)},
            files={'file': ('original.webm', expected[interview_id], 'video/webm')})
        elapsed = perf_counter() - started
        assert response.status_code == 200, response.text
        started = perf_counter()
        final = state.client.post(f'/medical-interviews/{interview_id}/recording/blocks/finalize', headers={**headers, 'X-Capture-Segment': attempt},
            json={'block_ids': [block_id], 'missing_message_ids': []})
        assert final.status_code == 200, final.text
        assert perf_counter() - started < 5
        return elapsed
    with ThreadPoolExecutor(max_workers=10) as pool:
        latencies = sorted(pool.map(preserve, captures))
    print(f'Synthetic block preservation P95={latencies[9]:.3f}s; ten independent interviews')
    assert latencies[9] < 2, f'Synthetic preservation P95={latencies[9]:.3f}s'
    with Session(state.engine) as db:
        blocks = db.query(InterviewRecordingBlockDB).all()
        assert len(blocks) == 10
        assert len({block.recording_id for block in blocks}) == 10
        assert len({block.sha256 for block in blocks}) == 10
        for block in blocks:
            recording = db.get(InterviewRecordingDB, block.recording_id)
            assert state.storage.resolve(block.storage_key).read_bytes() == expected[recording.medical_interview_id]


def test_greeting_three_exchanges_and_partial_recovery_keep_global_message_order(capture, exchange_agent, tmp_path):
    from app.routers import recording_blocks
    from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingSegmentDB, InterviewTurnDB, TurnVideoAnalysisDB
    state = capture
    state.client.app.include_router(recording_blocks.router)
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=state.id).one()
        recording.capture_config = {'mediaTransport': 'reusable_blocks_v1'}
        db.get(InterviewRecordingSegmentDB, state.segment_id).capture_config = {'mediaTransport': 'reusable_blocks_v1'}
        db.commit()
    source = tmp_path / 'exchange.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:r=10:d=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libvpx', '-c:a', 'libopus', '-threads', '1', str(source)], check=True, timeout=20)
    original = source.read_bytes()
    ids, message_ids = [], [state.greeting_id]
    for order in range(4):
        student_id = None
        patient_id = state.greeting_id
        if order:
            reply = state.client.post(f'/medical-interviews/{state.id}/messages', json={'content': f'Synthetic question {order}',
                'client_request_id': str(uuid4()), 'segment_id': state.segment_id})
            assert reply.status_code == 200, reply.text
            student_id, patient_id = reply.json()['new_message_ids']
            message_ids.extend([student_id, patient_id])
        block_id = str(uuid4()); ids.append(block_id)
        payload = {'capture_attempt_id': state.segment_id, 'order': order, 'duration_ms': 2000,
            'student_message_id': student_id, 'patient_message_id': patient_id,
            'student_speech': {'start_ms': 0, 'end_ms': 600} if order else None,
            'patient_playback': {'start_ms': 1400, 'end_ms': 1800}, 'patient_audio_missing': True}
        response = state.client.put(state.root + f'/blocks/{block_id}', data={'metadata': json.dumps(payload)}, files={'file': ('original.webm', original, 'video/webm')})
        assert response.status_code == 200, response.text
    final = state.client.post(state.root + '/blocks/finalize', json={'block_ids': ids, 'missing_message_ids': []})
    assert final.status_code == 200, final.text
    with Session(state.engine) as db:
        turns = db.query(InterviewTurnDB).filter_by(medical_interview_id=state.id).order_by(InterviewTurnDB.sequence).all()
        assert [turn.message_id for turn in turns] == message_ids
        for turn in turns:
            job = db.query(TurnVideoAnalysisDB).filter_by(turn_id=turn.id).one()
            if turn.speaker == 'student':
                assert job.result['block_source']['window'] == {'start_ms': 0, 'end_ms': 600}
                assert turn.end_ms - turn.start_ms == 600
        interview = db.get(MedicalInterviewDB, state.id)
        interview.status = 'processing'; db.commit()
    recap = state.client.get(f'/medical-interviews/{state.id}/recap')
    assert recap.status_code == 200, recap.text
    assert len(recap.json()['blocks']) == 4
    assert recap.json()['duration_ms'] == final.json()['duration_ms']
    assert 'student_video_source' not in recap.json()
