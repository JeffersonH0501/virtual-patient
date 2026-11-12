"""Catalog write permissions without live data."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.personality import Personality
from app.models.user import UserRole
from app.routers import personalities


@pytest.fixture
def catalog_api():
    app = FastAPI()
    app.include_router(personalities.router)
    actor = SimpleNamespace(id=1, role=UserRole.ADMIN)
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: actor
    with patch.object(personalities, "PersonalityController") as controller:
        personality = Personality(id=1, name="Synthetic personality", namespace_key="synthetic")
        controller.return_value.create_personality.return_value = personality
        controller.return_value.update_personality.return_value = personality
        controller.return_value.delete_personality.return_value = True
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, actor, db, controller


WRITES = [
    ("POST", "/personalities", {"name": "New personality", "namespace_key": "new"}),
    ("POST", "/personalities/1", {"namespace_key": "changed"}),
    ("DELETE", "/personalities/1", None),
]


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.DOCTOR])
@pytest.mark.parametrize("method,path,body", WRITES)
def test_catalog_writes_require_admin_before_mutation(catalog_api, role, method, path, body):
    client, actor, db, controller = catalog_api
    actor.role = role
    response = client.request(method, path, json=body)
    assert response.status_code == 403, response.text
    db.commit.assert_not_called()
    controller.assert_not_called()


@pytest.mark.parametrize("method,path,body", WRITES)
def test_catalog_writes_require_authentication(catalog_api, method, path, body):
    client, _, db, controller = catalog_api
    client.app.dependency_overrides.pop(get_current_active_user)
    assert client.request(method, path, json=body).status_code == 401
    db.commit.assert_not_called()
    controller.assert_not_called()


@pytest.mark.parametrize("method,path,body", WRITES)
def test_authorized_catalog_writes_remain_available(catalog_api, method, path, body):
    client, _, _, _ = catalog_api
    response = client.request(method, path, json=body)
    assert response.status_code == (201 if method == "POST" and path == "/personalities"
                                    else 204 if method == "DELETE" else 200), response.text
