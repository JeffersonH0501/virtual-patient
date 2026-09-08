"""Provision the single deployment-managed superuser account."""

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_password_hash, verify_password
from app.core.config import settings
from app.models.organization import OrganizationDB
from app.models.user import UserDB, UserRole


def synchronize_superuser(session: Session) -> str:
    """Create or update the sole superuser from environment configuration."""
    configured_values = {
        "SUPERUSER_EMAIL": settings.superuser_email,
        "SUPERUSER_PASSWORD": settings.superuser_password,
    }
    missing = [name for name, value in configured_values.items() if not value]
    if missing:
        raise RuntimeError(
            "Superuser provisioning requires: " + ", ".join(missing)
        )
    try:
        TypeAdapter(EmailStr).validate_python(settings.superuser_email)
    except ValidationError as error:
        raise RuntimeError("SUPERUSER_EMAIL must be a valid email address") from error
    if settings.superuser_preferred_language not in {"en", "es"}:
        raise RuntimeError("SUPERUSER_PREFERRED_LANGUAGE must be 'en' or 'es'")

    superusers = session.scalars(
        select(UserDB).where(UserDB.role == UserRole.SUPERUSER)
    ).all()
    if len(superusers) > 1:
        raise RuntimeError(
            "More than one superuser exists. Resolve the duplicate accounts "
            "manually before starting the application again."
        )

    superuser = superusers[0] if superusers else None
    conflicting_user = session.scalars(
        select(UserDB).where(
            func.lower(UserDB.email) == settings.superuser_email
        )
    ).first()
    if conflicting_user is not None and conflicting_user is not superuser:
        raise RuntimeError(
            "The configured superuser email belongs to another "
            "account. Resolve the conflict manually."
        )

    created = superuser is None
    if created:
        if not settings.superuser_first_name or not settings.superuser_last_name:
            raise RuntimeError("New superusers require SUPERUSER_FIRST_NAME and SUPERUSER_LAST_NAME")
        organization = session.scalars(
            select(OrganizationDB)
            .where(OrganizationDB.active.is_(True))
            .order_by(OrganizationDB.id)
        ).first()
        if organization is None:
            raise RuntimeError("An active organization is required for the superuser")
        superuser = UserDB(
            disabled=False,
            role=UserRole.SUPERUSER,
            organization_id=organization.id,
            hashed_password=get_password_hash(settings.superuser_password),
        )
        session.add(superuser)

    changed = created
    desired_values = {
        "email": settings.superuser_email,
        "first_name": settings.superuser_first_name or superuser.first_name,
        "last_name": settings.superuser_last_name or superuser.last_name,
        "preferred_language": settings.superuser_preferred_language,
        "disabled": False,
    }
    for field, value in desired_values.items():
        if getattr(superuser, field) != value:
            setattr(superuser, field, value)
            changed = True

    if not created and not verify_password(
        settings.superuser_password, superuser.hashed_password
    ):
        superuser.hashed_password = get_password_hash(settings.superuser_password)
        changed = True

    if changed:
        session.commit()
        return f"Synchronized superuser: {superuser.id}"

    return f"Superuser already matches configuration: {superuser.id}"
