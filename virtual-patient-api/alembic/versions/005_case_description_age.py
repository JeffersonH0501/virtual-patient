"""Remove age from bundled catalog descriptions without changing clinical ages."""
from alembic import op
import sqlalchemy as sa

revision = "005_case_description_age"
down_revision = "004_self_ratings"
branch_labels = None
depends_on = None

DESCRIPTIONS = {
    "hypothyroidism": (
        ("Patient of 40 years with physical fatigue (asthenia) and multiple symptoms affecting daily activities.",
         "Patient with physical fatigue (asthenia) and multiple symptoms affecting daily activities."),
        ("Paciente de 40 años con fatiga física (astenia) y múltiples síntomas que afectan las actividades diarias.",
         "Paciente con fatiga física (astenia) y múltiples síntomas que afectan las actividades diarias."),
    ),
    "joint_pain": (
        ("Patient of 45 years with 8-week history of pain in hands and wrists",
         "Patient with 8-week history of pain in hands and wrists"),
        ("Paciente de 45 años con historia de 8 semanas de dolor en manos y muñecas.",
         "Paciente con historia de 8 semanas de dolor en manos y muñecas."),
    ),
}
LEGACY_TITLES = {"Hypothyroidism Case": "hypothyroidism", "Joint Pain Case": "joint_pain"}


def update_descriptions(reverse=False):
    cases = sa.table("clinical_cases", sa.column("id", sa.Integer), sa.column("case_key", sa.String),
                     sa.column("title", sa.String),
                     sa.column("case_type", sa.String), sa.column("description", sa.String),
                     sa.column("description_translations", sa.JSON))
    connection = op.get_bind()
    rows = connection.execute(sa.select(cases).where(
        sa.or_(cases.c.case_key.in_(DESCRIPTIONS),
               sa.and_(cases.c.case_key.is_(None), cases.c.title.in_(LEGACY_TITLES))),
        cases.c.case_type == "default",
    )).mappings().all()
    for row in rows:
        key = row["case_key"] or LEGACY_TITLES[row["title"]]
        replacements = dict((new, old) if reverse else (old, new) for old, new in DESCRIPTIONS[key])
        changes = {}
        if row["description"] in replacements:
            changes["description"] = replacements[row["description"]]
        translations = row["description_translations"] or {}
        updated = {language: replacements.get(value, value) for language, value in translations.items()}
        if updated != translations:
            changes["description_translations"] = updated
        if changes:
            connection.execute(cases.update().where(cases.c.id == row["id"]).values(**changes))


def upgrade():
    update_descriptions()


def downgrade():
    update_descriptions(reverse=True)
