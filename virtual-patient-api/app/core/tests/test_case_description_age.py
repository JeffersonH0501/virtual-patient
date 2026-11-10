"""Only bundled descriptions change; clinical ages and customized copy remain intact."""
import importlib.util
from pathlib import Path
import sqlalchemy as sa


def test_description_migration_preserves_case_data_and_is_idempotent(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "alembic/versions/005_case_description_age.py"
    spec = importlib.util.spec_from_file_location("case_description_age", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    cases = sa.Table("clinical_cases", metadata,
                     sa.Column("id", sa.Integer, primary_key=True), sa.Column("case_key", sa.String),
                     sa.Column("title", sa.String),
                     sa.Column("case_type", sa.String), sa.Column("description", sa.String),
                     sa.Column("description_translations", sa.JSON), sa.Column("age", sa.Integer))
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        rows = []
        for index, (key, pairs) in enumerate(migration.DESCRIPTIONS.items(), 1):
            rows.append(dict(id=index, case_key=key, title="Synthetic case", case_type="default", age=40 + index,
                             description=pairs[0][0], description_translations={"es": pairs[1][0], "fr": "Custom translation"}))
        rows.extend([
            dict(id=3, case_key="hypothyroidism", title="Synthetic custom case", case_type="custom", age=60,
                 description=rows[0]["description"], description_translations=rows[0]["description_translations"]),
            dict(id=4, case_key="joint_pain", title="Customized case", case_type="default", age=70,
                 description="Customized source", description_translations={"es": "Descripción personalizada"}),
            dict(id=5, case_key=None, title="Hypothyroidism Case", case_type="default", age=40,
                 description=rows[0]["description"], description_translations=rows[0]["description_translations"]),
        ])
        connection.execute(cases.insert(), rows)
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        migration.upgrade()
        updated = connection.execute(sa.select(cases).order_by(cases.c.id)).mappings().all()
        for original, current in zip(rows[:2], updated[:2]):
            pairs = migration.DESCRIPTIONS[original["case_key"]]
            assert current["description"] == pairs[0][1]
            assert current["description_translations"] == {"es": pairs[1][1], "fr": "Custom translation"}
            assert current["age"] == original["age"]
        assert [dict(row) for row in updated[2:4]] == rows[2:4]
        assert updated[4]["description"] == migration.DESCRIPTIONS["hypothyroidism"][0][1]
        assert updated[4]["description_translations"]["es"] == migration.DESCRIPTIONS["hypothyroidism"][1][1]
        assert updated[4]["age"] == 40 and updated[4]["case_key"] is None
        migration.downgrade()
        restored = connection.execute(sa.select(cases).order_by(cases.c.id)).mappings().all()
        assert [dict(row) for row in restored] == rows
