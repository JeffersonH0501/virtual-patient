"""Security checks for public user payloads."""

import pytest
from pydantic import ValidationError

from app.models.user import AdminUserCreate, UserCreate, UserRole, UserUpdate, User
from app.routers.users import require_superuser
from fastapi import HTTPException


def test_public_registration_defaults_to_student() -> None:
    assert UserCreate(email="new@example.org", name="New User", password="secret").role == UserRole.STUDENT


def test_admin_creation_cannot_create_superusers() -> None:
    for role in (UserRole.TEACHER, UserRole.STUDENT):
        assert AdminUserCreate(email="new@example.org", name="New User", password="secret", role=role).role == role
    with pytest.raises(ValidationError):
        AdminUserCreate(email="new@example.org", name="New User", password="secret", role="superuser")


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.TEACHER])
def test_management_rejects_non_superusers(role) -> None:
    user = User(id=1, email="user@example.org", name="User", role=role)
    with pytest.raises(HTTPException) as failure:
        require_superuser(user)
    assert failure.value.status_code == 403


def test_public_registration_rejects_superuser_role() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="attacker@example.org", name="New User", password="secret", role="superuser")


@pytest.mark.parametrize("field", ["role", "organization_id"])
def test_self_service_update_rejects_privilege_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({field: "superuser" if field == "role" else 99})


def test_public_registration_rejects_organization_assignment() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="cross-organization@example.org",
            name="New User",
            password="secret",
            organization_id=99,
        )
