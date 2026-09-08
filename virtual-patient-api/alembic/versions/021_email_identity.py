"""Use email identity and separate given/family names.

Existing full names remain intact in first_name; last_name starts empty.
The private archive exists only to restore retired fields on downgrade.
"""

from alembic import op
import sqlalchemy as sa
from pydantic import EmailStr, TypeAdapter, ValidationError

revision = "021_email_identity"
down_revision = "020_evaluation_scale_five"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, email FROM users")).all()
    seen = set()
    for row in rows:
        email = (row.email or "").strip().lower()
        try:
            TypeAdapter(EmailStr).validate_python(email)
        except ValidationError as error:
            raise RuntimeError(
                f"Account {row.id} needs a valid email before identity migration"
            ) from error
        if email in seen:
            raise RuntimeError("Resolve duplicate case-insensitive emails before identity migration")
        seen.add(email)

    op.create_table(
        "user_identity_migration_archive",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("username", sa.String()),
        sa.Column("full_name", sa.String()),
        sa.Column("email", sa.String()),
    )
    op.execute(sa.text("""
        INSERT INTO user_identity_migration_archive (user_id, username, full_name, email)
        SELECT id, username, full_name, email FROM users
    """))
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.execute(sa.text("""
        UPDATE users SET first_name = COALESCE(full_name, ''),
                         last_name = '', email = lower(trim(email))
    """))
    op.alter_column("users", "first_name", nullable=False)
    op.alter_column("users", "last_name", nullable=False)
    op.alter_column("users", "email", nullable=False)
    op.create_index("uq_users_email_normalized", "users", [sa.text("lower(email)")], unique=True)
    op.drop_column("users", "username")
    op.drop_column("users", "full_name")


def downgrade():
    connection = op.get_bind()
    archive_exists = sa.inspect(connection).has_table("user_identity_migration_archive")
    op.add_column("users", sa.Column("username", sa.String(), nullable=True))
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))
    op.execute(sa.text("""
        UPDATE users SET username = 'restored-user-' || id::text,
                         full_name = trim(concat_ws(' ', first_name, last_name))
    """))
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.alter_column("users", "email", nullable=True)
    if archive_exists:
        op.execute(sa.text("""
            UPDATE users SET username = archive.username,
                             full_name = archive.full_name,
                             email = archive.email
            FROM user_identity_migration_archive AS archive
            WHERE users.id = archive.user_id
        """))
        op.drop_table("user_identity_migration_archive")
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
