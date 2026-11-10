"""Default-only catalog policy, without changing historical case records."""
from unittest.mock import patch

import pytest

from app.models.clinical_case import CaseType, ClinicalCaseDB
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserRole
from app.routers import clinical_cases
from app.routers.tests.test_organization_interview_history import history_api


@pytest.fixture
def catalog(history_api):
    client, actor, organization, _ = history_api
    client.app.include_router(clinical_cases.router)
    db = client.history_db
    cases = [
        ClinicalCaseDB(title="Default catalog fixture", description="Synthetic", case_type=CaseType.DEFAULT, active=True),
        ClinicalCaseDB(title="Custom catalog fixture", description="Synthetic", case_type=CaseType.CUSTOM, organization_id=organization, active=True),
        ClinicalCaseDB(title="Inactive catalog fixture", description="Synthetic", case_type=CaseType.DEFAULT, active=False),
    ]
    db.add_all(cases)
    db.commit()
    return client, actor, cases


@pytest.mark.parametrize("role", list(UserRole))
def test_only_active_default_cases_are_readable(catalog, role):
    client, actor, cases = catalog
    actor.role = role
    default, custom, inactive = cases
    for path in ("/clinical-cases", "/clinical-cases/default"):
        response = client.get(path)
        assert response.status_code == 200
        ids = {case["id"] for case in response.json()}
        assert default.id in ids
        assert custom.id not in ids
        assert inactive.id not in ids
    assert client.get(f"/clinical-cases/{default.id}").status_code == 200
    for case in (custom, inactive):
        for suffix in ("", "/languages", "/translation-status"):
            assert client.get(f"/clinical-cases/{case.id}{suffix}").status_code == 404
    assert client.get("/clinical-cases?case_type=custom").json() == []


@pytest.mark.parametrize("role", list(UserRole))
def test_case_authoring_endpoints_are_absent_for_every_role(catalog, role):
    client, actor, cases = catalog
    actor.role = role
    for case in cases:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, f"/clinical-cases/{case.id}", json={}).status_code == 405
        assert client.post(f"/clinical-cases/{case.id}/translations/title", json={}).status_code == 404
    assert client.post("/clinical-cases", json={}).status_code == 405
    assert client.get(f"/clinical-cases/organization/{actor.organization_id}").status_code == 404


@pytest.mark.parametrize("index", [1, 2])
def test_new_interviews_reject_custom_or_inactive_cases(catalog, index):
    client, actor, cases = catalog
    actor.role = UserRole.STUDENT
    with patch("app.routers.medical_interviews.MedicalInterviewController") as controller:
        controller.return_value.get_active_started_interview.return_value = None
        response = client.post("/medical-interviews", json={
            "clinical_case_id": cases[index].id,
            "patient_response_language": "es",
        })
        assert response.status_code == 404
        controller.return_value.create_interview.assert_not_called()


def test_retrying_draft_creation_returns_the_same_interview(catalog):
    client, actor, cases = catalog
    actor.role = UserRole.STUDENT
    db = client.history_db
    db.query(MedicalInterviewDB).filter_by(user_id=actor.id).update({"start_time": None})
    db.commit()
    payload = {
        "clinical_case_id": cases[0].id,
        "draft_request_id": "d0d488fc-9657-4d44-aea6-9213371df260",
    }
    first = client.post("/medical-interviews", json=payload)
    retry = client.post("/medical-interviews", json=payload)
    assert first.status_code == 201, first.text
    assert retry.status_code == 201, retry.text
    assert first.json()["interview"]["id"] == retry.json()["interview"]["id"]
    assert client.history_db.query(MedicalInterviewDB).filter_by(
        user_id=actor.id, clinical_case_id=cases[0].id,
    ).count() == 1
