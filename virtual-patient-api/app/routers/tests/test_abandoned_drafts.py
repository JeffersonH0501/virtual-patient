"""Remove abandoned preparation drafts while preserving active interviews."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria

from app.media.calibration_cleanup import cleanup_abandoned_interview_drafts
from app.media.storage import LocalMediaStorage
from app.models.medical_interview import MedicalInterviewDB, InterviewStatus
from app.routers.tests.test_organization_interview_history import history_api


def test_cleanup_removes_discarded_and_expired_drafts_but_keeps_active(history_api, tmp_path, monkeypatch):
    client, _, organization, _ = history_api
    db = client.history_db
    source = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.start_time.is_(None)).first()
    now = datetime.now(timezone.utc)
    def draft(created, metadata=None, started=None):
        return MedicalInterviewDB(user_id=source.user_id, clinical_case_id=source.clinical_case_id,
            status=InterviewStatus.IN_PROGRESS, start_time=started, created_at=created, interview_metadata=metadata)
    discarded = draft(now, {"calibration_discarded": True})
    expired = draft(now - timedelta(hours=2))
    active = draft(now)
    started = draft(now - timedelta(hours=2), started=now)
    db.add_all([discarded, expired, active, started]); db.flush()
    ids = [item.id for item in (discarded, expired, active, started)]
    db.commit()
    storage = LocalMediaStorage(tmp_path)
    monkeypatch.setattr('app.media.calibration.get_media_storage', lambda: storage)
    monkeypatch.setattr('app.controllers.administrative_deletion.get_media_storage', lambda: storage)
    def isolate(execute_state):
        if execute_state.is_select:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(MedicalInterviewDB, MedicalInterviewDB.id.in_(ids)))
    event.listen(db, 'do_orm_execute', isolate)
    try:
        assert cleanup_abandoned_interview_drafts(db, now=now) == 2
        assert cleanup_abandoned_interview_drafts(db, now=now, dry_run=False) == 2
        db.expire_all()
        assert db.get(MedicalInterviewDB, ids[0]) is None
        assert db.get(MedicalInterviewDB, ids[1]) is None
        assert db.get(MedicalInterviewDB, ids[2]) is not None
        assert db.get(MedicalInterviewDB, ids[3]) is not None
    finally:
        event.remove(db, 'do_orm_execute', isolate)
