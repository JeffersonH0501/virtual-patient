"""Independent review actions preserve results and reject overlapping jobs."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import interview_recordings as routes


@pytest.mark.parametrize("observations", [True, False])
def test_refresh_queues_only_the_selected_operation(observations):
    recording = SimpleNamespace(id="recording-id", capture_config={
        "observation_processing": {"status": "complete"},
        "evaluation_processing": {"status": "complete"},
    })
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = recording
    with patch.object(routes, "_get_interview", return_value=SimpleNamespace(status="completed")), patch.object(routes, "_require_analysis_admin") as admin, patch.object(routes, "_recording_response", return_value="response"):
        assert routes._queue_review_refresh(7, "superuser", db, observations=observations) == "response"
    admin.assert_called_once()
    selected = "observation_processing" if observations else "evaluation_processing"
    untouched = "evaluation_processing" if observations else "observation_processing"
    assert recording.capture_config[selected]["status"] == "queued"
    assert recording.capture_config[untouched]["status"] == ("queued" if observations else "complete")
    job = db.add.call_args.args[0]
    assert job.kind == ("observations" if observations else "evaluation")
    assert job.payload == {"recording_id": "recording-id"}


@pytest.mark.parametrize("pending_key", ["observation_processing", "evaluation_processing", "learning_moments"])
@pytest.mark.parametrize("observations", [True, False])
def test_pending_work_blocks_both_actions(pending_key, observations):
    recording = SimpleNamespace(id="recording-id", capture_config={pending_key: {"status": "processing"}})
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = recording
    with patch.object(routes, "_get_interview", return_value=SimpleNamespace(status="completed")), patch.object(routes, "_require_analysis_admin"):
        with pytest.raises(HTTPException) as error:
            routes._queue_review_refresh(7, "superuser", db, observations=observations)
    assert error.value.status_code == 409
    db.commit.assert_not_called()
