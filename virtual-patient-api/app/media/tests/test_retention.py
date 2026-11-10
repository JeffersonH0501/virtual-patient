"""Calendar expiry preserves the authorized twelve-month maximum."""
from datetime import datetime, timezone
import pytest
from app.media.retention import media_retention_deadline
from app.media.retention import purge_expired_media
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_twelve_months_handles_leap_day():
    started = datetime(2024, 2, 29, 10, tzinfo=timezone.utc)
    assert media_retention_deadline(started) == datetime(2025, 2, 28, 10, tzinfo=timezone.utc)


def test_shorter_policy_handles_month_end():
    started = datetime(2026, 1, 31, 10, tzinfo=timezone.utc)
    assert media_retention_deadline(started, 1) == datetime(2026, 2, 28, 10, tzinfo=timezone.utc)


def test_policy_cannot_exceed_authorized_maximum():
    with pytest.raises(ValueError):
        media_retention_deadline(datetime.now(timezone.utc), 13)


def test_expiry_preview_is_read_only_and_apply_covers_legacy_rows():
    expired = SimpleNamespace(id="expired", medical_interview_id=1, started_at=datetime(2024, 1, 1, tzinfo=timezone.utc), retention_expires_at=None, status="ready", assets=[])
    recent = SimpleNamespace(id="recent", medical_interview_id=2, started_at=datetime(2026, 6, 1, tzinfo=timezone.utc), retention_expires_at=datetime(2028, 1, 1, tzinfo=timezone.utc), status="ready", assets=[])
    db = MagicMock()
    db.query.return_value.yield_per.return_value = [expired, recent]
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    assert purge_expired_media(db, now=now) == 1
    assert expired.retention_expires_at is None
    db.commit.assert_not_called()
    with patch("app.media.retention.get_media_storage") as storage:
        assert purge_expired_media(db, dry_run=False, now=now) == 1
        storage.return_value.delete_recording.assert_called_once_with(1, "expired")
    assert expired.status == "unavailable"
    assert recent.retention_expires_at == datetime(2027, 6, 1, tzinfo=timezone.utc)


def test_purge_continues_and_retries_a_recording_after_disk_error():
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    expired = [
        SimpleNamespace(id=f"recording-{i}", medical_interview_id=i, status="ready",
                        assets=[SimpleNamespace(status="ready")],
                        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc), retention_expires_at=None)
        for i in (1, 2)
    ]
    db = MagicMock()
    db.query.return_value.yield_per.return_value = expired
    with patch("app.media.retention.get_media_storage") as storage:
        delete = storage.return_value.delete_recording
        delete.side_effect = [OSError("synthetic file failure"), None, None, None]
        assert purge_expired_media(db, dry_run=False, now=now) == 2
        assert all(row.status == row.assets[0].status == "unavailable" for row in expired)
        assert purge_expired_media(db, dry_run=False, now=now) == 2
        assert [call.args for call in delete.call_args_list] == [
            (1, "recording-1"), (2, "recording-2"), (1, "recording-1"), (2, "recording-2"),
        ]
