"""Simplify the hypothyroidism catalog description without changing clinical data."""
from alembic import op
import sqlalchemy as sa

revision = "006_case_description_wording"
down_revision = "005_case_description_age"
branch_labels = None
depends_on = None


def update_wording(reverse=False):
    for original, simplified in (("physical fatigue (asthenia)", "physical fatigue"),
                                 ("fatiga física (astenia)", "fatiga física")):
        old, new = (simplified, original) if reverse else (original, simplified)
        op.get_bind().execute(sa.text("""
            UPDATE clinical_cases
            SET description = replace(description, :old, :new),
                description_translations = (
                    SELECT coalesce(json_object_agg(key, replace(value, :old, :new)), description_translations)
                    FROM json_each_text(description_translations)
                )
            WHERE case_type = 'default' AND
                (case_key = 'hypothyroidism' OR (case_key IS NULL AND title = 'Hypothyroidism Case'))
        """), {"old": old, "new": new})


def upgrade():
    update_wording()


def downgrade():
    update_wording(reverse=True)
