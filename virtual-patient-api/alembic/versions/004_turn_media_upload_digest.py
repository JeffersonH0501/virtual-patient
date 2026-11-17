"""Record the digest of the uploaded bytes next to the stored replay file.

Turn originals are rewritten losslessly (stream copy) for seekable replay, so
``sha256`` covers the stored file and ``upload_sha256`` the browser upload.
Revision 003 creates the table from the current ORM metadata, so a clean
install already has the column.
"""
from alembic import op
import sqlalchemy as sa

revision = "004_turn_media_upload_digest"
down_revision = "003_per_turn_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("interview_turn_media")}
    if "upload_sha256" not in columns:
        op.add_column("interview_turn_media", sa.Column("upload_sha256", sa.String(length=64), nullable=True))
        op.execute("UPDATE interview_turn_media SET upload_sha256 = sha256")
        op.alter_column("interview_turn_media", "upload_sha256", nullable=False)


def downgrade() -> None:
    op.drop_column("interview_turn_media", "upload_sha256")
