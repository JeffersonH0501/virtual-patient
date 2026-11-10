"""Calibration reference persistence, access and retention on isolated DB rows."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.media.storage import LocalMediaStorage, get_media_storage
from app.media.retention import purge_expired_calibration_media
from app.models.calibration_capture import CalibrationCaptureDB
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserDB, UserRole
from app.routers import calibration, interview_recordings
from app.routers.tests.test_organization_interview_history import history_api
from app.multimodal.tests.test_calibration import _valid_metadata_json, _VIDEO_RESULT_PASS


@pytest.fixture
def reference_api(history_api, tmp_path, monkeypatch):
    client, admin, _, _ = history_api
    db = client.history_db
    interview = db.query(MedicalInterviewDB).join(UserDB).filter(MedicalInterviewDB.start_time.is_(None), UserDB.organization_id == admin.organization_id).first()
    owner = SimpleNamespace(id=interview.user_id, role=UserRole.STUDENT, organization_id=admin.organization_id)
    actor = SimpleNamespace(user=admin)
    from sqlalchemy import event
    from sqlalchemy.orm import with_loader_criteria
    identifier = interview.id
    def isolate_interview_queries(execute_state):
        if execute_state.is_select:
            execute_state.statement = execute_state.statement.options(with_loader_criteria(MedicalInterviewDB, MedicalInterviewDB.id == identifier))
    event.listen(db, 'do_orm_execute', isolate_interview_queries)
    storage = LocalMediaStorage(tmp_path)
    monkeypatch.setattr('app.media.calibration.get_media_storage', lambda: storage)
    monkeypatch.setattr('app.media.retention.get_media_storage', lambda: storage)
    monkeypatch.setattr('app.media.calibration_cleanup.get_media_storage', lambda: storage)
    monkeypatch.setattr('app.controllers.administrative_deletion.get_media_storage', lambda: storage)
    worker = AsyncMock(return_value=(_VIDEO_RESULT_PASS.copy(), .01))
    monkeypatch.setattr(calibration, '_run_timed_worker', worker)
    app = FastAPI()
    app.include_router(calibration.router)
    app.include_router(interview_recordings.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: owner
    app.dependency_overrides[interview_recordings._current_media_user] = lambda: actor.user
    app.dependency_overrides[get_media_storage] = lambda: storage
    try:
        with TestClient(app) as api:
            yield api, db, interview, owner, actor, storage, worker
    finally:
        event.remove(db, 'do_orm_execute', isolate_interview_queries)


def upload(api, interview_id, content=b'synthetic calibration reference', **overrides):
    fields = dict(stage='gaze', interview_id=str(interview_id), duration_ms='23000', metadata_json=_valid_metadata_json())
    fields.update(overrides)
    return api.post('/calibration/process-stage', data=fields, files={'media': ('capture.webm', content, 'video/webm')})


@pytest.mark.parametrize("role,test_mode,allowed",[(UserRole.STUDENT,True,False),(UserRole.SUPERUSER,False,False),(UserRole.SUPERUSER,True,True)])
def test_quality_bypass_is_server_scoped_to_owned_superuser_tests(reference_api,role,test_mode,allowed):
    from app.nonverbal.tests.test_independent_mediapipe import poor_calibration,frame
    from app.nonverbal.mediapipe_calibration import build_profile,build_camera_reference
    from app.models.calibration import CameraCalibrationMetadata
    from app.multimodal.calibration_attestation import verify_calibration_checkpoints
    from fastapi import HTTPException
    api,db,interview,owner,_,_,worker=reference_api
    owner.role=role
    interview.interview_metadata={**(interview.interview_metadata or {}),"calibration_test":test_mode}
    db.commit()
    observations,metadata=poor_calibration()
    payload=metadata.model_dump(mode="json")
    payload.update(camera_reference_start_ms=15000,camera_reference_end_ms=20000,experimental_quality_bypass=True)
    async def process(path,parsed,stage):
        if stage=="guided": return {"passed":True,"guided_checks":{"phases":[]}},.01
        gaze_result=build_profile(observations,parsed)
        result={"passed":False,"failed_stage":"gaze","gaze":gaze_result,"experimental_quality_bypass":False}
        if gaze_result["profile"]:
            cm=CameraCalibrationMetadata(gaze_source=parsed.gaze_source,geometry=parsed.geometry,geometry_stable=True,
                affine_matrix=gaze_result["profile"]["affine_matrix"],experimental_quality_bypass=parsed.experimental_quality_bypass)
            result.update(camera=build_camera_reference([frame(t,y=-.06) for t in range(15000,20000,100)],cm),
                camera_metadata=cm.model_dump(mode="json"),experimental_quality_bypass=True)
        return result,.01
    worker.side_effect=process
    response=upload(api,interview.id,stage="unified",duration_ms="20000",metadata_json=json.dumps(payload))
    assert response.status_code==200,response.text
    data=response.json()
    assert worker.call_args.args[1].experimental_quality_bypass is allowed
    assert data["status"]==("passed" if allowed else "failed")
    gaze_checkpoint=data["result"]["checkpoints"]["gaze"]
    assert gaze_checkpoint["result"]["passed"] is False
    assert bool(gaze_checkpoint["attestation"]) is allowed
    if allowed:
        tokens={k:v["attestation"] for k,v in data["result"]["checkpoints"].items()}
        with pytest.raises(HTTPException): verify_calibration_checkpoints(owner.id,interview.id,tokens)
        assert verify_calibration_checkpoints(owner.id,interview.id,tokens,allow_experimental=True)["profile"]["experimental_only"]
        from app.nonverbal.tests.test_guided_checks import guided_metadata
        original=guided_metadata(); offset=original["guided_checks"][0]["start_ms"]
        intervals=[{k:v-offset if k!="kind" else v for k,v in item.items()} for item in original["guided_checks"]]
        guided_payload={"geometry":metadata.geometry.model_dump(mode="json"),"geometry_stable":True,
            "guided_checks":intervals,"guided_environment":original["guided_environment"],"attestations":tokens}
        guided=upload(api,interview.id,stage="guided",duration_ms=str(intervals[-1]["end_ms"]),metadata_json=json.dumps(guided_payload))
        assert guided.status_code==200,guided.text
        assert worker.call_args.args[1].profile["experimental_only"]


def test_separate_guided_capture_requires_accepted_server_checkpoints(reference_api, monkeypatch):
    from app.nonverbal.tests.test_guided_checks import guided_metadata
    api, db, interview, owner, _, _, worker = reference_api
    owner.role = UserRole.SUPERUSER
    interview.interview_metadata = {**(interview.interview_metadata or {}), "calibration_test": True}
    db.commit()
    assert upload(api, interview.id).status_code == 200
    camera_capture = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    original = guided_metadata()
    offset = original["guided_checks"][0]["start_ms"]
    intervals = [{key: value - offset if key != "kind" else value for key, value in item.items()}
                 for item in original["guided_checks"]]
    metadata = {"geometry": original["geometry"], "geometry_stable": True,
        "guided_checks": intervals, "guided_environment": original["guided_environment"],
        "attestations": {"gaze": "invalid", "camera": "invalid"}, "profile": {"forged": True}}
    worker.reset_mock()
    response = upload(api, interview.id, stage="guided", duration_ms=str(intervals[-1]["end_ms"]), metadata_json=json.dumps(metadata))
    assert response.status_code == 422
    worker.assert_not_called()
    from app.models.calibration import CalibrationGeometry
    verified_profile = {"capture_geometry": CalibrationGeometry.model_validate(original["geometry"]).model_dump(mode="json"), "affine_matrix": [[1,0,0],[0,1,0]]}
    monkeypatch.setattr("app.multimodal.calibration_attestation.verify_calibration_checkpoints",
        lambda *args, **kwargs: {"profile": verified_profile, "capture_ids": {"camera": camera_capture.id}})
    worker.return_value = ({"passed": True, "guided_checks": {"phases": []}}, .01)
    response = upload(api, interview.id, stage="guided", duration_ms=str(intervals[-1]["end_ms"]), metadata_json=json.dumps(metadata))
    assert response.status_code == 200, response.text
    assert response.json()["attestation"] is None
    assert response.json()["result"]["guided_checks"]["processing_time_seconds"] == .01
    worker.assert_called_once()
    assert worker.call_args.args[1].profile == verified_profile
    assert worker.call_args.args[1].attestations == {}
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).count() == 2


def test_calibration_tests_survive_exit_and_abandoned_draft_cleanup(reference_api):
    from app.media.calibration_cleanup import cleanup_calibration_references
    api, db, interview, _, _, storage, _ = reference_api
    response = upload(api, interview.id)
    assert response.status_code == 200
    interview.interview_metadata = {**interview.interview_metadata, 'calibration_test': True}
    db.commit()
    capture = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    path = storage.resolve(capture.storage_key)
    result = capture.result
    assert api.delete(f'/calibration/drafts/{interview.id}').status_code == 409
    cleanup_calibration_references(db, dry_run=False, now=datetime.now(timezone.utc)+timedelta(hours=2))
    db.expire_all()
    assert db.get(CalibrationCaptureDB, capture.id).result == result
    assert path.read_bytes() == b'synthetic calibration reference'
    assert interview.start_time is None


def test_saved_calibration_tests_are_listed_only_for_the_authenticated_superuser_owner(reference_api):
    api, db, interview, owner, _, _, _ = reference_api
    upload(api, interview.id)
    interview.interview_metadata = {**interview.interview_metadata, 'calibration_test': True}
    db.commit()
    assert api.get('/calibration/tests').status_code == 403
    owner.role = UserRole.SUPERUSER
    assert api.get('/calibration/tests').json()['tests'][0]['interview_id'] == interview.id
    owner.id += 1
    assert api.get('/calibration/tests').json()['tests'] == []


def test_guided_results_are_returned_and_retained_with_the_private_original(reference_api):
    import json
    from app.nonverbal.tests.test_guided_checks import guided_metadata
    api, db, interview, _, _, _, worker = reference_api
    metadata = guided_metadata()
    diagnostics = {"version": "guided_checks_v1", "diagnostic_only": True, "prompt_labels_verified": False, "phases": []}
    worker.return_value = ({"passed": True, "failed_stage": None, "gaze": dict(_VIDEO_RESULT_PASS),
        "camera": dict(_VIDEO_RESULT_PASS), "camera_metadata": {"geometry": metadata["geometry"],
        "geometry_stable": True, "affine_matrix": [[1,0,0],[0,1,0]]}, "guided_checks": diagnostics}, .01)
    response = upload(api, interview.id, stage='unified',
        duration_ms=str(metadata['guided_checks'][-1]['end_ms']), metadata_json=json.dumps(metadata))
    assert response.status_code == 200, response.text
    assert response.json()['result']['guided_checks'] == diagnostics
    capture = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    assert capture.capture_metadata['guided_checks'] == metadata['guided_checks']
    assert capture.capture_metadata['guided_environment'] == metadata['guided_environment']
    assert capture.result['guided_checks'] == diagnostics
    assert response.json()['result']['checkpoints']['gaze']['attestation']


def test_guided_windows_outside_the_uploaded_duration_are_rejected(reference_api):
    import json
    from app.nonverbal.tests.test_guided_checks import guided_metadata
    api, _, interview, _, _, _, worker = reference_api
    response = upload(api, interview.id, stage='unified', metadata_json=json.dumps(guided_metadata()))
    assert response.status_code == 422
    worker.assert_not_awaited()


def test_reference_survives_analysis_and_identical_upload_retry(reference_api):
    api, db, interview, _, _, storage, worker = reference_api
    response = upload(api, interview.id)
    assert response.status_code == 200, response.text
    identifier = response.json()['result']['capture_id']
    assert upload(api, interview.id).json()['result']['capture_id'] == identifier
    assert worker.await_count == 1
    capture = db.get(CalibrationCaptureDB, identifier)
    assert storage.resolve(capture.storage_key).read_bytes() == b'synthetic calibration reference'
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).count() == 1
    interview.interview_metadata = {'calibration': {'capture_ids': {'gaze': identifier}}}
    db.commit()
    listing = api.get(f'/medical-interviews/{interview.id}/calibration/captures').json()
    assert listing['captures'][0]['used_for'] == ['gaze']
    assert 'storage_key' not in listing['captures'][0]
    replay = api.get(listing['captures'][0]['media_url'], headers={'Range': 'bytes=0-8'})
    assert replay.status_code == 206 and replay.content == b'synthetic'
    assert replay.headers['cache-control'] == 'private, no-store'
    assert replay.headers['content-type'] == 'video/webm'


@pytest.mark.parametrize('worker_failure', [False, True])
def test_failed_analysis_keeps_original_and_outcome(reference_api, worker_failure):
    api, db, interview, _, _, storage, worker = reference_api
    if worker_failure:
        worker.side_effect = RuntimeError('Synthetic worker failure')
    else:
        worker.return_value = ({'passed': False, 'failure_reason': 'camera_unstable', 'quality': {'camera_radius_p90': .7}}, .01)
    response = upload(api, interview.id)
    assert response.status_code == 200 and response.json()['status'] == 'failed'
    capture = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    assert storage.resolve(capture.storage_key).exists()
    assert capture.result['passed'] is False


def test_capture_and_inspection_enforce_owner_role_and_organization(reference_api):
    api, db, interview, owner, actor, _, _ = reference_api
    owner.id += 1000000
    assert upload(api, interview.id).status_code == 404
    owner.id = interview.user_id
    assert upload(api, interview.id).status_code == 200
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    urls = [f'/medical-interviews/{interview.id}/calibration/captures', f'/medical-interviews/{interview.id}/calibration/captures/{row.id}/video']
    actor.user = owner
    for url in urls:
        assert api.get(url).status_code == 403
    actor.user = SimpleNamespace(id=owner.id + 1, role=UserRole.SUPERUSER, organization_id=owner.organization_id + 1)
    for url in urls:
        assert api.get(url).status_code == 403
    interview.start_time = datetime.now(timezone.utc)
    db.commit()
    assert upload(api, interview.id, b'new upload').status_code == 409


def test_expired_video_is_blocked_and_purged_without_removing_results(reference_api):
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    row.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()
    listing = api.get(f'/medical-interviews/{interview.id}/calibration/captures').json()
    assert listing['captures'][0]['media_url'] is None
    assert api.get(f'/medical-interviews/{interview.id}/calibration/captures/{row.id}/video').status_code == 410
    assert purge_expired_calibration_media(db) == 1
    assert storage.resolve(row.storage_key).exists()
    assert purge_expired_calibration_media(db, dry_run=False) == 1
    with pytest.raises(FileNotFoundError):
        storage.resolve(row.storage_key)
    assert row.result['passed'] is True


def test_interview_deletion_removes_calibration_rows_and_files(reference_api, monkeypatch):
    from app.controllers.administrative_deletion import delete_parent
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    capture_id, key = row.id, row.storage_key
    interview.status = 'interrupted'
    db.commit()
    monkeypatch.setattr('app.controllers.administrative_deletion.get_media_storage', lambda: storage)
    delete_parent(db, interview, 'interview')
    assert db.get(CalibrationCaptureDB, capture_id) is None
    with pytest.raises(FileNotFoundError):
        storage.resolve(key)


def test_discard_erases_only_calibration_captures_results_and_rejects_late_upload(reference_api):
    api, db, interview, owner, _, storage, _ = reference_api
    upload(api, interview.id)
    identifier = interview.id
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).one()
    key = row.storage_key
    owner.id += 1000000
    assert api.delete(f'/calibration/drafts/{identifier}').status_code == 404
    owner.id = interview.user_id
    assert api.delete(f'/calibration/drafts/{identifier}').status_code == 204
    assert db.get(MedicalInterviewDB, identifier) is not None
    assert db.get(MedicalInterviewDB, identifier).interview_metadata.get('calibration') is None
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).count() == 0
    with pytest.raises(FileNotFoundError):
        storage.resolve(key)
    assert api.delete(f'/calibration/drafts/{identifier}').status_code == 204
    assert upload(api, identifier).status_code == 410


def test_discard_preserves_an_interview_after_it_has_started(reference_api):
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    interview.start_time = datetime.now(timezone.utc)
    interview.status = 'interrupted'
    db.commit()
    assert api.delete(f'/calibration/drafts/{interview.id}').status_code == 409
    assert storage.resolve(row.storage_key).exists()


def test_cleanup_removes_inactive_drafts_and_old_orphans_but_keeps_active_and_started_captures(reference_api):
    import os
    from app.media.calibration_cleanup import cleanup_calibration_references
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id).one()
    identifier = interview.id
    now = datetime.now(timezone.utc)
    orphan = storage.root / 'interviews' / str(identifier) / 'calibration' / 'unconfirmed.webm'
    orphan.write_bytes(b'synthetic orphan')
    os.utime(orphan, (now.timestamp()-600, now.timestamp()-600))
    recent = orphan.with_name('in-flight.webm')
    recent.write_bytes(b'synthetic recent file')
    preview = cleanup_calibration_references(db, now=now)
    assert preview == {'calibrations': 0, 'orphan_files': 1}
    assert orphan.exists()
    assert cleanup_calibration_references(db, dry_run=False, now=now) == preview
    assert not orphan.exists() and recent.exists()
    assert storage.resolve(row.storage_key).exists()
    # A started interview remains protected even after its draft activity expires.
    interview = db.get(MedicalInterviewDB, identifier)
    interview.start_time = now
    interview.status = 'interrupted'
    db.commit()
    assert cleanup_calibration_references(db, dry_run=False, now=now+timedelta(hours=2))['calibrations'] == 0
    assert storage.resolve(row.storage_key).exists()
    # Simulate an abandoned preparation, without touching any started fixture.
    interview.start_time = None
    interview.status = 'in_progress'
    db.commit()
    assert cleanup_calibration_references(db, dry_run=False, now=now+timedelta(hours=2))['calibrations'] == 1
    assert db.get(MedicalInterviewDB, identifier) is not None
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).count() == 0


def test_cleanup_rechecks_reference_under_interview_lock_and_retries_erasure(reference_api, monkeypatch):
    import os
    from app.media.calibration_cleanup import cleanup_calibration_references
    from app.controllers.interview_lifecycle import lock_row as actual_lock
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    identifier = interview.id
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).one()
    now = datetime.now(timezone.utc)
    original = row.storage_key
    def publish_before_lock(db, model, key):
        record = actual_lock(db, model, key)
        # The confirmed capture must remain referenced when the scan acquires its lock.
        assert db.query(CalibrationCaptureDB).filter_by(storage_key=original).first() is not None
        return record
    monkeypatch.setattr('app.media.calibration_cleanup.lock_row', publish_before_lock)
    orphan = storage.root / 'interviews' / str(identifier) / 'calibration' / 'retry.webm'
    orphan.write_bytes(b'synthetic orphan')
    os.utime(orphan, (now.timestamp()-600, now.timestamp()-600))
    real_delete = storage.delete
    monkeypatch.setattr(storage, 'delete', lambda key: (_ for _ in ()).throw(OSError('Synthetic erasure failure')))
    cleanup_calibration_references(db, dry_run=False, now=now)
    assert orphan.exists() and storage.resolve(original).exists()
    monkeypatch.setattr(storage, 'delete', real_delete)
    cleanup_calibration_references(db, dry_run=False, now=now)
    assert not orphan.exists() and storage.resolve(original).exists()


def test_discard_during_analysis_cannot_publish_a_late_result(reference_api):
    api, db, interview, owner, _, storage, worker = reference_api
    identifier = interview.id
    async def finish_after_discard(*args):
        calibration.discard_calibration_draft(identifier, current_user=owner, db=db)
        return (_VIDEO_RESULT_PASS.copy(), .01)
    worker.side_effect = finish_after_discard
    assert upload(api, identifier).status_code == 409
    assert db.get(MedicalInterviewDB, identifier) is not None
    assert db.get(MedicalInterviewDB, identifier).interview_metadata.get('calibration') is None
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).count() == 0
    assert not list((storage.root/'interviews'/str(identifier)).glob('calibration/*'))


def test_identical_retry_refreshes_draft_activity_without_duplicating_capture(reference_api):
    from app.media.calibration_cleanup import cleanup_calibration_references
    api, db, interview, _, _, _, worker = reference_api
    upload(api, interview.id)
    identifier = interview.id
    interview.interview_metadata = {**interview.interview_metadata, 'calibration_activity_at': (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()}
    row = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).one()
    row.created_at = datetime.now(timezone.utc)-timedelta(hours=2)
    db.commit()
    assert upload(api, identifier).status_code == 200
    assert worker.await_count == 1
    assert cleanup_calibration_references(db)['calibrations'] == 0


def test_orphan_scan_covers_missing_interviews_without_touching_other_media(reference_api):
    import os
    from app.media.calibration_cleanup import cleanup_calibration_references
    _, _, interview, _, _, storage, _ = reference_api
    directory = storage.root/'interviews'/str(interview.id+100000000)/'calibration'
    directory.mkdir(parents=True)
    orphan = directory/'unconfirmed.webm'
    orphan.write_bytes(b'synthetic unlinked file')
    old = datetime.now(timezone.utc).timestamp()-600
    os.utime(orphan, (old, old))
    other = directory.parent/'recording'/'other-video.webm'
    other.parent.mkdir()
    other.write_bytes(b'synthetic non-calibration recording')
    result = cleanup_calibration_references(reference_api[1], dry_run=False)
    assert result['orphan_files'] == 1
    assert not orphan.exists() and other.exists()


def test_failed_calibration_erasure_is_invalidated_then_retried_without_deleting_interview(reference_api, monkeypatch):
    from app.media.calibration_cleanup import cleanup_calibration_references
    api, db, interview, _, _, storage, _ = reference_api
    upload(api, interview.id)
    identifier = interview.id
    other = storage.root/'interviews'/str(identifier)/'other-media'
    other.mkdir()
    (other/'keep.txt').write_text('Synthetic unrelated interview content')
    interview.interview_metadata = {**interview.interview_metadata, 'unrelated_field': 'preserved', 'calibration': {'status': 'passed'}}
    db.commit()
    real_delete = storage.delete_recording
    def fail_erasure(*args):
        raise OSError('Synthetic calibration erasure failure')
    monkeypatch.setattr(storage, 'delete_recording', fail_erasure)
    assert api.delete(f'/calibration/drafts/{identifier}').status_code == 503
    current = db.get(MedicalInterviewDB, identifier)
    assert current is not None
    assert current.interview_metadata['unrelated_field'] == 'preserved'
    assert 'calibration' not in current.interview_metadata
    assert 'calibration_activity_at' not in current.interview_metadata
    assert db.query(CalibrationCaptureDB).filter_by(medical_interview_id=identifier).count() == 0
    assert upload(api, identifier).status_code == 410
    monkeypatch.setattr(storage, 'delete_recording', real_delete)
    assert cleanup_calibration_references(db, dry_run=False)['calibrations'] == 1
    assert (other/'keep.txt').exists()
    assert not list((storage.root/'interviews'/str(identifier)).glob('calibration/*'))


def test_a_late_profile_save_cannot_restore_discarded_calibration(reference_api):
    import asyncio
    from fastapi import HTTPException
    from app.routers.medical_interviews import CalibrationResultRequest, save_calibration_result
    from app.multimodal.tests.test_calibration import draft_payload
    api, db, interview, owner, _, _, _ = reference_api
    identifier = interview.id
    upload(api, identifier)
    assert api.delete(f'/calibration/drafts/{identifier}').status_code == 204
    with pytest.raises(HTTPException) as error:
        asyncio.run(save_calibration_result(identifier, CalibrationResultRequest.model_validate(draft_payload()), current_user=owner, db=db))
    assert error.value.status_code == 410
    assert db.get(MedicalInterviewDB, identifier).interview_metadata.get('calibration') is None
