"""Shared validation and preservation boundaries on the canonical transport."""
import json
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy.orm import Session

from app.models.recording_block import InterviewRecordingBlockDB
from app.routers import recording_blocks
from app.routers.tests.test_recording_blocks import capture, legacy_capture
from app.routers.tests.test_lifecycle_integrity import lifecycle_api, exchange_agent


def upload(state, *, identifier=None, content=b'Synthetic incomplete original', **metadata):
    state.client.app.include_router(recording_blocks.router)
    body = {'capture_attempt_id': state.segment_id, 'order': 0, 'duration_ms': 1000,
            'patient_message_id': state.greeting_id, 'patient_audio_missing': True, **metadata}
    return state.client.put(state.root + '/blocks/' + (identifier or str(uuid4())),
        data={'metadata': json.dumps(body)}, files={'file': ('original.webm', content, 'video/webm')})


def test_invalid_roi_is_rejected_before_private_storage(capture, monkeypatch):
    saved = []
    async def unexpected_save(*args, **kwargs):
        saved.append(True)
        raise AssertionError('Invalid ROI reached storage')
    monkeypatch.setattr(capture.storage, 'save_upload', unexpected_save)
    assert upload(capture, patient_roi_snapshots=[None]).status_code == 422
    assert saved == []


def test_original_upload_limit_is_enforced_before_publication(capture, monkeypatch):
    from app.media.storage import RECORDING_FILE_LIMITS
    monkeypatch.setitem(RECORDING_FILE_LIMITS, 'student_video', 5)
    assert upload(capture).status_code == 413
    with Session(capture.engine) as db:
        assert db.query(InterviewRecordingBlockDB).count() == 0


def test_failed_storage_keeps_preexisting_confirmed_original(capture, monkeypatch):
    first = upload(capture)
    assert first.status_code == 200
    with Session(capture.engine) as db:
        original = db.query(InterviewRecordingBlockDB).one()
        key = original.storage_key
        content = capture.storage.resolve(key).read_bytes()
    async def fail_storage(*args, **kwargs):
        raise OSError('Synthetic storage failure')
    monkeypatch.setattr(capture.storage, 'save_upload', fail_storage)
    with pytest.raises(OSError):
        upload(capture, order=1, recovery=True)
    assert capture.storage.resolve(key).read_bytes() == content
    with Session(capture.engine) as db:
        assert db.query(InterviewRecordingBlockDB).count() == 1


def test_failed_commit_removes_only_unconfirmed_original(capture, monkeypatch):
    first = upload(capture)
    assert first.status_code == 200
    with Session(capture.engine) as db:
        key = db.query(InterviewRecordingBlockDB).one().storage_key
    def fail_commit(db):
        raise ConnectionError('Synthetic failure before commit')
    monkeypatch.setattr(Session, 'commit', fail_commit)
    with pytest.raises(ConnectionError):
        upload(capture, order=1, recovery=True)
    assert capture.storage.resolve(key).read_bytes() == b'Synthetic incomplete original'
    with Session(capture.engine) as db:
        assert db.query(InterviewRecordingBlockDB).count() == 1
    assert len(list(capture.storage.resolve(key).parent.glob('*'))) == 1


def test_interruption_fences_retries_without_deleting_the_confirmed_original(capture):
    identifier = str(uuid4())
    first = upload(capture, identifier=identifier)
    assert first.status_code == 200
    assert upload(capture, identifier=identifier).json() == first.json()
    assert capture.client.post(f'/medical-interviews/{capture.id}/abandon').status_code == 200
    assert upload(capture, identifier=identifier).status_code == 409
    with Session(capture.engine) as db:
        block = db.get(InterviewRecordingBlockDB, identifier)
        assert capture.storage.resolve(block.storage_key).read_bytes() == b'Synthetic incomplete original'


def test_upload_rechecks_capture_authority_after_probe(capture, monkeypatch):
    entered, release = Event(), Event()
    def delayed_probe(_):
        entered.set()
        assert release.wait(10)
        return {'duration_ms': 1000, 'start_pts_ms': 0, 'end_pts_ms': 1000}
    monkeypatch.setattr(recording_blocks, 'probe_media_timing', delayed_probe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(upload, capture)
        assert entered.wait(10)
        try:
            assert capture.client.post(f'/medical-interviews/{capture.id}/abandon').status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 409
    with Session(capture.engine) as db:
        assert db.query(InterviewRecordingBlockDB).count() == 0
