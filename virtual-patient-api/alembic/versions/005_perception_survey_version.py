"""Record which questionnaire version each perception survey answers.

Existing rows keep ``NULL`` (answers from before versioning, never converted). Revision 001 creates the table
from the current ORM metadata, so a clean install already has the column.
"""
from alembic import op
import sqlalchemy as sa

revision = "005_perception_survey_version"
down_revision = "004_turn_media_upload_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("perception_surveys")}
    if "questionnaire_version" not in columns:
        op.add_column("perception_surveys", sa.Column("questionnaire_version", sa.String(length=48), nullable=True))


def downgrade() -> None:
    op.drop_column("perception_surveys", "questionnaire_version")
