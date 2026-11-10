"""Role boundaries for manual review analysis and technical turn observations."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.user import UserRole
from app.routers import interview_recordings as routes


@pytest.fixture
def analysis_api(monkeypatch):
    actor = SimpleNamespace(id=7, role=UserRole.STUDENT, organization_id=3)
    interview = SimpleNamespace(id=17, user_id=7, status="completed",
                                user=SimpleNamespace(id=7, organization_id=3))
    db = MagicMock()
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes._current_media_user] = lambda: actor
    app.dependency_overrides[routes.get_db] = lambda: db
    monkeypatch.setattr(routes, "_get_interview", lambda *_: interview)
    with TestClient(app) as client:
        yield client, actor, db


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
@pytest.mark.parametrize("operation", ["recording/reprocess", "evaluation/regenerate", "learning-moments/regenerate"])
def test_owners_cannot_manually_regenerate_analysis(analysis_api, role, operation):
    client, actor, db = analysis_api
    actor.role = role
    response = client.post(f"/medical-interviews/17/{operation}")
    assert response.status_code == 403
    db.commit.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize("operation", ["recording/reprocess", "evaluation/regenerate", "learning-moments/regenerate"])
def test_superusers_cannot_refresh_another_organization(analysis_api, operation):
    client, actor, db = analysis_api
    actor.id = 9
    actor.role = UserRole.SUPERUSER
    actor.organization_id = 4
    assert client.post(f"/medical-interviews/17/{operation}").status_code == 403
    db.commit.assert_not_called()


@pytest.mark.parametrize("operation, kind", [("recording/reprocess", "observations"), ("evaluation/regenerate", "evaluation")])
def test_superusers_can_refresh_interviews_they_do_not_own(analysis_api, monkeypatch, operation, kind):
    client, actor, db = analysis_api
    actor.id = 9
    actor.role = UserRole.SUPERUSER
    recording = SimpleNamespace(id="recording-id", medical_interview_id=17, status="ready", duration_ms=1000, capture_config={})
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = recording
    stage = MagicMock()
    monkeypatch.setattr(routes, "stage_processing_job", stage)
    response = client.post(f"/medical-interviews/17/{operation}")
    assert response.status_code == 200, response.text
    stage.assert_called_once_with(db, 17, kind, {"recording_id": "recording-id"})
    db.commit.assert_called_once()


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER, UserRole.SUPERUSER])
def test_recap_reserves_technical_evidence_for_superusers(analysis_api, monkeypatch, role):
    client, actor, db = analysis_api
    actor.role = role
    # All actors have assessment access here, including a teacher after submission.
    monkeypatch.setattr(routes, "can_read_assessments", lambda *_: True)
    turn = routes.RecapTurn(turn_id="turn-1", speaker="student", transcript="Synthetic transcript",
                            start_ms=0, end_ms=1000, input_source="synthetic", timing_source="synthetic",
                            timing_quality="measured", paraverbal={"status": "ok"}, nonverbal_features={"status": "ok"})
    monkeypatch.setattr(routes, "_recap_turns", lambda *_: [turn])
    db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/medical-interviews/17/recap")
    assert response.status_code == 200, response.text
    result = response.json()["turns"][0]
    assert result["transcript"] == "Synthetic transcript"
    assert result["start_ms"] == 0
    assert result["paraverbal"] == ({"status": "ok"} if role == UserRole.SUPERUSER else None)
    assert result["nonverbal_features"] == ({"status": "ok"} if role == UserRole.SUPERUSER else None)
