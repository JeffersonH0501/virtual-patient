"""Security checks for public user payloads."""

import pytest
from pydantic import ValidationError

from app.models.user import UserCreate, UserRole, UserUpdate


def test_public_registration_accepts_student_and_teacher_roles() -> None:
    for role in (UserRole.STUDENT, UserRole.TEACHER):
        request = UserCreate(email=f"new-{role.value}@example.org", first_name="New", last_name="User", password="secret", role=role)
        assert request.role == role


def test_public_registration_rejects_superuser_role() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="attacker@example.org", first_name="New", last_name="User", password="secret", role="superuser")


@pytest.mark.parametrize("field", ["role", "organization_id"])
def test_self_service_update_rejects_privilege_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({field: "superuser" if field == "role" else 99})


def test_public_registration_rejects_organization_assignment() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="cross-organization@example.org",
            first_name="New",
            last_name="User",
            password="secret",
            organization_id=99,
        )
