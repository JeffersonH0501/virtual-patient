"""Catalog write permissions and organization response contracts without live data."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.personality import Personality
from app.models.user import UserRole
from app.routers import organizations, personalities


@pytest.fixture
def catalog_api():
    app = FastAPI()
    app.include_router(organizations.router)
    app.include_router(personalities.router)
    actor = SimpleNamespace(id=1, role=UserRole.SUPERUSER, organization_id=7)
    row = SimpleNamespace(id=7, name="Synthetic organization", description=None,
                          active=True, created_at=None, updated_at=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    db.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = [row]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: actor
    with patch.object(personalities, "PersonalityController") as controller:
        personality = Personality(id=1, name="Synthetic personality", namespace_key="synthetic")
        controller.return_value.create_personality.return_value = personality
        controller.return_value.update_personality.return_value = personality
        controller.return_value.delete_personality.return_value = True
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, actor, db, row, controller


WRITES = [
    ("POST", "/organizations", {"id": 9, "name": "New organization"}),
    ("POST", "/organizations/7", {"name": "Changed organization"}),
    ("DELETE", "/organizations/7", None),
    ("POST", "/personalities", {"name": "New personality", "namespace_key": "new"}),
    ("POST", "/personalities/1", {"namespace_key": "changed"}),
    ("DELETE", "/personalities/1", None),
]


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
@pytest.mark.parametrize("method,path,body", WRITES)
def test_catalog_writes_require_superuser_before_mutation(catalog_api, role, method, path, body):
    client, actor, db, row, controller = catalog_api
    actor.role = role
    response = client.request(method, path, json=body)
    assert response.status_code == 403, response.text
    db.commit.assert_not_called()
    controller.assert_not_called()
    assert row.name == "Synthetic organization" and row.active is True


@pytest.mark.parametrize("method,path,body", WRITES)
def test_catalog_writes_require_authentication(catalog_api, method, path, body):
    client, _, db, _, controller = catalog_api
    client.app.dependency_overrides.pop(get_current_active_user)
    assert client.request(method, path, json=body).status_code == 401
    db.commit.assert_not_called()
    controller.assert_not_called()


@pytest.mark.parametrize("organization_id", [None, 8])
@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_superuser_cannot_change_another_organization(catalog_api, organization_id, method):
    client, actor, db, _, _ = catalog_api
    actor.organization_id = organization_id
    assert client.request(method, "/organizations/7", json={"name": "Changed"}).status_code == 403
    db.query.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("method,path,body", WRITES)
def test_authorized_catalog_writes_remain_available(catalog_api, method, path, body):
    client, _, db, row, _ = catalog_api
    if path == "/organizations":
        db.query.return_value.filter.return_value.first.return_value = None
    response = client.request(method, path, json=body)
    assert response.status_code == (201 if path in {"/organizations", "/personalities"}
                                    else 204 if method == "DELETE" and path.startswith("/personalities")
                                    else 200), response.text
    if path == "/organizations/7":
        assert row.name == "Changed organization" if method == "POST" else row.active is False


@pytest.mark.parametrize("path", ["/organizations", "/organizations/7"])
def test_organization_reads_serialize_real_orm_timestamps(catalog_api, path):
    client, _, _, row, _ = catalog_api
    row.created_at = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    row.updated_at = row.created_at
    response = client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()[0] if path == "/organizations" else response.json()
    assert datetime.fromisoformat(data["created_at"]) == row.created_at
    assert datetime.fromisoformat(data["updated_at"]) == row.updated_at


def test_organization_update_returns_timestamps_after_commit(catalog_api):
    client, _, db, row, _ = catalog_api
    row.created_at = row.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    response = client.post("/organizations/7", json={"name": "Updated"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Updated"
    assert datetime.fromisoformat(response.json()["updated_at"]) == row.updated_at
    db.commit.assert_called_once()
