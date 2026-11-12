"""Provision the single deployment-managed administrator account."""

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_password_hash, verify_password
from app.core.config import settings
from app.models.user import UserDB, UserRole


def synchronize_admin(session: Session) -> str:
    """Create or update the sole administrator from environment configuration."""
    configured_values = {
        "ADMIN_EMAIL": settings.admin_email,
        "ADMIN_PASSWORD": settings.admin_password,
    }
    missing = [name for name, value in configured_values.items() if not value]
    if missing:
        raise RuntimeError(
            "Admin provisioning requires: " + ", ".join(missing)
        )
    try:
        TypeAdapter(EmailStr).validate_python(settings.admin_email)
    except ValidationError as error:
        raise RuntimeError("ADMIN_EMAIL must be a valid email address") from error
    if settings.admin_preferred_language not in {"en", "es"}:
        raise RuntimeError("ADMIN_PREFERRED_LANGUAGE must be 'en' or 'es'")

    admins = session.scalars(
        select(UserDB).where(UserDB.role == UserRole.ADMIN)
    ).all()
    if len(admins) > 1:
        raise RuntimeError(
            "More than one administrator exists. Resolve the duplicate accounts "
            "manually before starting the application again."
        )

    admin = admins[0] if admins else None
    conflicting_user = session.scalars(
        select(UserDB).where(
            func.lower(UserDB.email) == settings.admin_email
        )
    ).first()
    if conflicting_user is not None and conflicting_user is not admin:
        raise RuntimeError(
            "The configured admin email belongs to another "
            "account. Resolve the conflict manually."
        )

    created = admin is None
    if created:
        if not settings.admin_name:
            raise RuntimeError("New admins require ADMIN_NAME")
        admin = UserDB(
            disabled=False,
            role=UserRole.ADMIN,
            hashed_password=get_password_hash(settings.admin_password),
        )
        session.add(admin)

    changed = created
    desired_values = {
        "email": settings.admin_email,
        "name": settings.admin_name or admin.name,
        "preferred_language": settings.admin_preferred_language,
        "disabled": False,
    }
    for field, value in desired_values.items():
        if getattr(admin, field) != value:
            setattr(admin, field, value)
            changed = True

    if not created and not verify_password(
        settings.admin_password, admin.hashed_password
    ):
        admin.hashed_password = get_password_hash(settings.admin_password)
        changed = True

    if changed:
        session.commit()
        return f"Synchronized admin: {admin.id}"

    return f"Admin already matches configuration: {admin.id}"
