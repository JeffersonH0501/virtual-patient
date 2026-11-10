"""Adopt the frozen release baseline for the former Alembic head."""

import json
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

PREVIOUS_HEAD = "033_teacher_grading"
BASELINE = "001_release_baseline"

LEGACY_DEFAULTS = {
    ("medical_interviews", "status"): "'IN_PROGRESS'::interview_status",
    ("progress_summaries", "localized_versions"): "'{}'::jsonb",
    ("progress_summaries", "source_language"): "'en'::character varying",
    ("turn_video_analyses", "roi_snapshots"): "'[]'::json",
    ("turn_video_analyses", "status"): "'queued'::character varying",
}
LEGACY_NAMES = {
    ("turn_video_analyses", "index", "ix_turn_video_analyses_interview"):
        "ix_turn_video_analyses_medical_interview_id",
    ("turn_video_analyses", "index", "ix_turn_video_analyses_recording"):
        "ix_turn_video_analyses_recording_id",
    ("turn_video_analyses", "index", "uq_turn_video_analyses_turn_id"):
        "ix_turn_video_analyses_turn_id",
    ("turn_video_analyses", "constraint", "uq_turn_video_analyses_storage_key"):
        "turn_video_analyses_storage_key_key",
    ("turn_video_analyses", "index", "uq_turn_video_analyses_storage_key"):
        "turn_video_analyses_storage_key_key",
    ("users", "constraint", "fk_users_organization_id"): "users_organization_id_fkey",
}
LEGACY_REDUNDANCIES = {
    ("interview_recordings", "constraint", "interview_recordings_medical_interview_id_key",
     '["UNIQUE (medical_interview_id)", true]'),
    ("interview_recordings", "index", "interview_recordings_medical_interview_id_key",
     '["CREATE UNIQUE INDEX interview_recordings_medical_interview_id_key ON interview_recordings '
     'USING btree (medical_interview_id)", true, true]'),
    ("turn_video_analyses", "constraint", "uq_turn_video_analyses_turn_id", '["UNIQUE (turn_id)", true]'),
}

# Compare definitions, not OIDs or column order. Ignore unrelated tables such
# as LangGraph's separately managed persistence and historical private archives.
SCHEMA_DEFINITIONS = text("""
    WITH tables AS (
        SELECT oid, relname, relkind
        FROM pg_class
        WHERE relnamespace = current_schema()::regnamespace AND relname = ANY(:tables)
    )
    SELECT relname, 'table', relname, relkind::text FROM tables
    UNION ALL
    SELECT t.relname, 'column', a.attname,
           json_build_array(format_type(a.atttypid, a.atttypmod), a.attnotnull,
                            pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated)::text
    FROM tables t
    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum > 0 AND NOT a.attisdropped
    LEFT JOIN pg_attrdef d ON d.adrelid = t.oid AND d.adnum = a.attnum
    UNION ALL
    SELECT t.relname, 'constraint', c.conname,
           json_build_array(pg_get_constraintdef(c.oid), c.convalidated)::text
    FROM tables t JOIN pg_constraint c ON c.conrelid = t.oid
    UNION ALL
    SELECT t.relname, 'index', i.relname,
           json_build_array(
               replace(pg_get_indexdef(i.oid), ' ON ' || quote_ident(current_schema()) || '.', ' ON '),
               x.indisvalid, x.indisready
           )::text
    FROM tables t JOIN pg_index x ON x.indrelid = t.oid
    JOIN pg_class i ON i.oid = x.indexrelid
    UNION ALL
    SELECT t.relname, 'trigger', g.tgname,
           json_build_array(
               replace(pg_get_triggerdef(g.oid), quote_ident(current_schema()) || '.', ''),
               g.tgenabled, p.prosrc, p.prosecdef, p.proconfig, l.lanname,
               p.pronamespace = current_schema()::regnamespace
           )::text
    FROM tables t JOIN pg_trigger g ON g.tgrelid = t.oid AND NOT g.tgisinternal
    JOIN pg_proc p ON p.oid = g.tgfoid
    JOIN pg_language l ON l.oid = p.prolang
    UNION ALL
    SELECT typ.typname, 'enum', typ.typname,
           json_agg(e.enumlabel ORDER BY e.enumsortorder)::text
    FROM pg_type typ JOIN pg_enum e ON e.enumtypid = typ.oid
    WHERE typ.typnamespace = current_schema()::regnamespace
      AND typ.typname IN ('case_type', 'interview_status', 'user_role')
    GROUP BY typ.typname
""")


def normalize_legacy_definitions(definitions) -> set:
    """Accept the equivalent definitions left by the older incremental DDL."""
    normalized = set()
    for table, kind, name, definition in definitions - LEGACY_REDUNDANCIES:
        default = LEGACY_DEFAULTS.get((table, name))
        if kind == "column" and default is not None:
            attributes = json.loads(definition)
            if attributes[2] == default:
                attributes[2] = None
                definition = json.dumps(attributes)
        canonical_name = LEGACY_NAMES.get((table, kind, name), name)
        if kind == "index" and canonical_name != name:
            definition = definition.replace(f"INDEX {name} ON", f"INDEX {canonical_name} ON", 1)
        normalized.add((table, kind, canonical_name, definition))
    return normalized


def adopt_release_baseline(connection, config) -> None:
    revision = ScriptDirectory.from_config(config).get_revision(BASELINE).module
    operations = Operations(MigrationContext.configure(connection))
    schema = connection.scalar(text("SELECT current_schema()"))
    tables = set(inspect(connection).get_table_names(schema=schema))

    # The old fresh-install path stamped the head after creating ORM tables.
    # That path omitted the job table and the database-only snapshot trigger.
    if "medical_interviews" in tables and "interview_processing_jobs" not in tables:
        revision.create_processing_jobs(operations)
    if "interview_evaluation_runs" in tables and not connection.scalar(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = 'interview_evaluation_runs'::regclass
              AND tgname = 'evaluation_runs_append_only'
        )
    """)):
        revision.install_evaluation_run_trigger(operations)

    reference_schema = f"release_baseline_{uuid4().hex}"
    with connection.begin_nested() as reference:
        connection.execute(text(f'CREATE SCHEMA "{reference_schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{reference_schema}"'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        reference_tables = inspect(connection).get_table_names(schema=reference_schema)
        expected = set(connection.execute(SCHEMA_DEFINITIONS, {"tables": reference_tables}))
        reference.rollback()

    actual = normalize_legacy_definitions(
        set(connection.execute(SCHEMA_DEFINITIONS, {"tables": reference_tables}))
    )
    if actual != expected:
        differences = ", ".join(sorted({row[0] for row in actual ^ expected}))
        raise RuntimeError(
            f"Revision {PREVIOUS_HEAD} does not match the release schema in: {differences}. "
            "Keep the database on the previous deployment and reconcile the schema from a backup "
            "or verified copy before adopting the baseline."
        )

    connection.execute(
        text("UPDATE alembic_version SET version_num = :baseline WHERE version_num = :previous"),
        {"baseline": BASELINE, "previous": PREVIOUS_HEAD},
    )
