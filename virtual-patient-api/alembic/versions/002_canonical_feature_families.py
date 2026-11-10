"""Normalize feature family identifiers without changing stored measurements."""

import json

from alembic import op

revision = "002_canonical_feature_families"
down_revision = "001_release_baseline"
branch_labels = None
depends_on = None

FAMILIES = {
    "temporal": "speech_timing",
    "prosodic_modulation": "prosodic_variability",
    "visual_orientation": "gaze_orientation",
    "head_gestural_feedback": "head_nods",
    "facial_expressivity": "smile_activity",
}

LABELS = {
    **{
        f"{prefix}_visual_orientation": f"{prefix}_gaze_orientation"
        for prefix in ("sustained", "scarce", "fragmented", "typical")
    },
    **{
        f"{prefix}_facial_expressivity": f"{prefix}_smile_activity"
        for prefix in ("absent", "marked", "frequent", "moderate", "scarce")
    },
    "mixed_visual_orientation_unclassified": "mixed_gaze_orientation_unclassified",
    "mixed_facial_expressivity_unclassified": "mixed_smile_activity_unclassified",
    "mixed_head_gestural_feedback_unclassified": "mixed_head_nods_unclassified",
    "typical_temporal_pattern": "typical_speech_timing_pattern",
    "mixed_temporal_pattern_unclassified": "mixed_speech_timing_pattern_unclassified",
    "mixed_modulation_unclassified": "mixed_prosodic_variability_unclassified",
}


def _rewrite(families, labels, evidence):
    op.execute("""
        CREATE FUNCTION pg_temp.rename_feature_families(value jsonb, names jsonb)
        RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
        DECLARE
            result jsonb;
        BEGIN
            CASE jsonb_typeof(value)
                WHEN 'object' THEN
                    IF EXISTS (
                        SELECT 1 FROM jsonb_object_keys(value) AS k(key)
                        GROUP BY coalesce(names->>key, key) HAVING count(*) > 1
                    ) THEN
                        RAISE EXCEPTION 'Feature family rename would overwrite data';
                    END IF;
                    SELECT coalesce(jsonb_object_agg(
                        coalesce(names->>key, key),
                        pg_temp.rename_feature_families(item, names)), '{}'::jsonb)
                    INTO result FROM jsonb_each(value) AS fields(key, item);
                WHEN 'array' THEN
                    SELECT coalesce(jsonb_agg(
                        pg_temp.rename_feature_families(item, names) ORDER BY position), '[]'::jsonb)
                    INTO result FROM jsonb_array_elements(value) WITH ORDINALITY AS entries(item, position);
                WHEN 'string' THEN
                    result := coalesce(names->(value #>> '{}'), value);
                ELSE
                    result := value;
            END CASE;
            RETURN result;
        END;
        $$;
    """)
    names = json.dumps({**families, **labels})
    for column in ("paraverbal", "nonverbal_features"):
        for layer in ("base_labels", "integrated_labels"):
            op.execute(f"""
                UPDATE interview_turns
                SET {column} = jsonb_set({column}::jsonb, '{{{layer}}}',
                    pg_temp.rename_feature_families({column}::jsonb->'{layer}', '{names}'::jsonb))::json
                WHERE jsonb_typeof({column}::jsonb->'{layer}') = 'object'
                  AND {column}::jsonb->'{layer}' IS DISTINCT FROM
                    pg_temp.rename_feature_families({column}::jsonb->'{layer}', '{names}'::jsonb)
            """)
    names = json.dumps(evidence)
    op.execute(f"""
        UPDATE interview_recordings
        SET capture_config = jsonb_set(capture_config::jsonb, '{{learning_moments,moments}}',
            (SELECT coalesce(jsonb_agg(
                CASE WHEN jsonb_typeof(moment->'evidence_used') = 'array'
                    THEN jsonb_set(moment, '{{evidence_used}}',
                        pg_temp.rename_feature_families(moment->'evidence_used', '{names}'::jsonb))
                    ELSE moment END ORDER BY position), '[]'::jsonb)
             FROM jsonb_array_elements(capture_config::jsonb #> '{{learning_moments,moments}}')
                 WITH ORDINALITY AS moments(moment, position)))::json
        WHERE jsonb_typeof(capture_config::jsonb #> '{{learning_moments,moments}}') = 'array'
    """)
    op.execute("DROP FUNCTION pg_temp.rename_feature_families(jsonb, jsonb)")


def upgrade():
    _rewrite(FAMILIES, LABELS, {**FAMILIES, "smile_behavior": "smile_activity"})


def downgrade():
    _rewrite(
        {new: old for old, new in FAMILIES.items()},
        {new: old for old, new in LABELS.items()},
        {**{new: old for old, new in FAMILIES.items()}, "smile_activity": "smile_behavior"},
    )