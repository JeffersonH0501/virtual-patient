"""HTTP authorization, organization ownership and safe account responses."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.user import User, UserDB, UserRole
from app.routers.users import router, get_db, get_current_active_user
from app.core.auth import verify_password
from app.core.captcha import require_captcha
from sqlalchemy import text


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    UserDB.__table__.create(engine)
    with Session(engine) as db:

        db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_active_user] = lambda: User(id=99, name="Admin", email="admin@example.org", role=UserRole.ADMIN)
        with TestClient(app) as client:
            yield app, client, db
    engine.dispose()


def test_admin_creates_teacher_without_returning_token_or_password(api):
    _, client, db = api
    payload = dict(name="Teacher", email="TEACHER@example.org", password="test-password", role="doctor")
    response = client.post("/users/admin", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "doctor"
    assert "access_token" not in data and "hashed_password" not in data
    stored = db.query(UserDB).one()
    assert stored.hashed_password != payload["password"]
    assert client.post("/users/admin", json=payload).status_code in (400, 409)
    db.add(UserDB(name="Other", email="other@example.org", hashed_password="test", role=UserRole.STUDENT))
    db.commit()
    assert {item["email"] for item in client.get("/users/admin").json()} == {"teacher@example.org", "other@example.org"}


@pytest.mark.parametrize("role", ["student", "doctor"])
def test_non_superusers_cannot_manage_accounts(api, role):
    app, client, _ = api
    app.dependency_overrides[get_current_active_user] = lambda: User(id=1, name="User", email="user@example.org", role=role)
    assert client.get("/users/admin").status_code == 403
    assert client.post("/users/admin", json=dict(name="Teacher", email="teacher@example.org", password="test", role="doctor")).status_code == 403


@pytest.mark.parametrize("role", ["student", "doctor"])
def test_public_registration_creates_account_in_default_organization(api, role):
    app, client, db = api
    app.dependency_overrides.pop(get_current_active_user)
    app.dependency_overrides[require_captcha] = lambda: None
    academic = {"semester_range": "first_four", "university": "Example University"} if role == "student" else {}
    response = client.post("/users", json=dict(name="New User", email="new@example.org", password="test-password", role=role, **academic))
    assert response.status_code == 201
    assert response.json()["access_token"]
    stored = db.query(UserDB).one()
    assert stored.role == role
    assert stored.semester_range == academic.get("semester_range")
    assert stored.university == academic.get("university")


@pytest.mark.parametrize("academic", [
    {}, {"semester_range": "first_four"}, {"university": "University"},
    {"semester_range": "invalid", "university": "University"},
    {"semester_range": "ninth_plus", "university": "   "},
])
def test_public_student_registration_rejects_invalid_academic_information(api, academic):
    app, client, db = api
    app.dependency_overrides[require_captcha] = lambda: None
    response = client.post("/users", json={"name": "Student", "email": "student@example.org", "password": "secret", "role": "student", **academic})
    assert response.status_code == 422
    assert db.query(UserDB).count() == 0

def create_account(client):
    response = client.post("/users/admin", json=dict(
        name="Student", email="student@example.org", password="original", role="student",
    ))
    assert response.status_code == 201
    return response.json()["id"]


def test_admin_updates_identity_role_and_password_without_exposing_secrets(api):
    _, client, db = api
    account_id = create_account(client)
    response = client.patch(f"/users/admin/{account_id}", json=dict(
        name=" Updated Name ", email=" UPDATED@example.org ", role="doctor", password=" new password ",
    ))
    assert response.status_code == 200
    account = response.json()
    assert account["name"] == "Updated Name"
    assert account["email"] == "updated@example.org"
    assert account["role"] == "doctor"
    assert not {"password", "hashed_password", "access_token", "refresh_token"}.intersection(account)
    stored = db.get(UserDB, account_id)
    assert verify_password(" new password ", stored.hashed_password)
    assert not verify_password("original", stored.hashed_password)


def test_partial_update_keeps_password_and_unchanged_fields(api):
    _, client, db = api
    account_id = create_account(client)
    previous_hash = db.get(UserDB, account_id).hashed_password
    response = client.patch(f"/users/admin/{account_id}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["email"] == "student@example.org"
    assert response.json()["role"] == "student"
    assert db.get(UserDB, account_id).hashed_password == previous_hash


def test_admin_updates_student_academic_information(api):
    _, client, db = api
    account_id = create_account(client)
    response = client.patch(f"/users/admin/{account_id}", json={"semester_range": "ninth_plus", "university": "  Example University  "})
    assert response.status_code == 200
    assert response.json()["semester_range"] == "ninth_plus"
    assert response.json()["university"] == "Example University"
    assert db.get(UserDB, account_id).university == "Example University"
    assert client.patch(f"/users/admin/{account_id}", json={"semester_range": "invalid"}).status_code == 422
    assert client.patch(f"/users/admin/{account_id}", json={"university": " "}).status_code == 422
    assert client.patch(f"/users/admin/{account_id}", json={"role": "teacher", "university": "University"}).status_code == 422


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"email": "invalid"}, {"password": ""}, {"password": "  "},
    {"role": "admin"}, {"role": "invalid"}, {"organization_id": 2}, {"disabled": True},
    {"name": None}, {"email": None}, {"role": None}, {"password": None},
])
def test_update_rejects_invalid_or_privileged_fields(api, changes):
    _, client, _ = api
    account_id = create_account(client)
    assert client.patch(f"/users/admin/{account_id}", json=changes).status_code == 422


def test_update_checks_email_conflicts_and_rolls_back_other_changes(api):
    _, client, db = api
    account_id = create_account(client)
    client.post("/users/admin", json=dict(name="Other", email="other@example.org", password="test", role="doctor"))
    response = client.patch(f"/users/admin/{account_id}", json={"email": "OTHER@example.org", "name": "Should not persist"})
    assert response.status_code == 409
    assert db.get(UserDB, account_id).name == "Student"
    assert client.patch(f"/users/admin/{account_id}", json={"email": "STUDENT@example.org"}).status_code == 200


def test_update_can_target_students_but_not_admin_or_missing_accounts(api):
    _, client, db = api
    db.add_all([
        UserDB(id=10, name="Other", email="other@example.org", hashed_password="test", role=UserRole.STUDENT),
        UserDB(id=11, name="Admin", email="admin@example.org", hashed_password="test", role=UserRole.ADMIN),
    ])
    db.commit()
    assert client.patch("/users/admin/10", json={"name": "Updated"}).status_code == 200
    for account_id in (11, 999):
        assert client.patch(f"/users/admin/{account_id}", json={"name": "Forbidden"}).status_code == 404


@pytest.mark.parametrize("role", ["student", "doctor"])
def test_update_requires_superuser(api, role):
    app, client, _ = api
    account_id = create_account(client)
    app.dependency_overrides[get_current_active_user] = lambda: User(
        id=99, name="User", email="user@example.org", role=role,
    )
    assert client.patch(f"/users/admin/{account_id}", json={"role": "doctor"}).status_code == 403


def test_update_requires_authentication(api):
    app, client, _ = api
    app.dependency_overrides.pop(get_current_active_user)
    assert client.patch("/users/admin/1", json={"name": "Forbidden"}).status_code == 401


def test_list_returns_scoped_total_independent_of_page_size(api):
    _, client, db = api
    assert client.get("/users/admin").headers["X-Total-Count"] == "0"
    create_account(client)
    client.post("/users/admin", json=dict(name="Teacher", email="teacher@example.org", password="test", role="doctor"))
    db.add_all([
        UserDB(name="Other", email="other@example.org", hashed_password="test", role=UserRole.STUDENT),
        UserDB(name="Admin", email="admin@example.org", hashed_password="test", role=UserRole.ADMIN),
    ])
    db.commit()
    for offset in (0, 1, 2, 3):
        response = client.get(f"/users/admin?offset={offset}&limit=1")
        assert response.status_code == 200
        assert response.headers["X-Total-Count"] == "3"
        assert len(response.json()) == (0 if offset == 3 else 1)


def test_registration_date_is_generated_and_cannot_be_edited(api):
    _, client, _ = api
    response = client.post("/users/admin", json=dict(
        name="New account", email="new@example.org", password="test", role="student",
    ))
    assert response.status_code == 201
    account = response.json()
    assert account["created_at"] is not None
    updated = client.patch(f"/users/admin/{account['id']}", json={"name": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["created_at"] == account["created_at"]
    assert client.patch(f"/users/admin/{account['id']}", json={"created_at": "2000-01-01T00:00:00Z"}).status_code == 422


def test_legacy_registration_date_remains_unknown(api):
    _, client, db = api
    account_id = create_account(client)
    db.execute(text("UPDATE users SET created_at = NULL WHERE id = :id"), {"id": account_id})
    db.commit()
    db.expire_all()
    assert client.get("/users/admin").json()[0]["created_at"] is None
