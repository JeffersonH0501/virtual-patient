"""Promote Py-Feat observations and normalize feature names.

Revision ID: 022_pyfeat_primary
Revises: 021_email_identity
"""

from alembic import op
import sqlalchemy as sa


revision = "022_pyfeat_primary"
down_revision = "021_email_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE interview_turns
        SET nonverbal_features = CASE
            WHEN pyfeat_nonverbal_features IS NULL THEN NULL
            ELSE jsonb_strip_nulls(
                pyfeat_nonverbal_features::jsonb
                - 'visual_alignment_dwell_ms'
                - 'smile_intensity_mean'
                || jsonb_build_object(
                    'median_visual_alignment_dwell_ms',
                    COALESCE(
                        pyfeat_nonverbal_features::jsonb -> 'median_visual_alignment_dwell_ms',
                        pyfeat_nonverbal_features::jsonb -> 'visual_alignment_dwell_ms'
                    ),
                    'mean_smile_activation',
                    COALESCE(
                        pyfeat_nonverbal_features::jsonb -> 'mean_smile_activation',
                        pyfeat_nonverbal_features::jsonb -> 'smile_intensity_mean'
                    )
                )
            )::json
        END
    """))
    connection.execute(sa.text("""
        UPDATE interview_turns
        SET paraverbal = (
            paraverbal::jsonb
            - 'speaking_rate_wpm'
            - 'pause_total_ms'
            - 'pause_median_ms'
            - 'pause_ratio'
            - 'f0_median_hz'
            - 'f0_iqr_st'
            - 'loudness_median_rel'
            - 'loudness_iqr'
            || jsonb_strip_nulls(jsonb_build_object(
                'speech_rate_wpm', paraverbal::jsonb -> 'speaking_rate_wpm',
                'total_pause_duration_ms', paraverbal::jsonb -> 'pause_total_ms',
                'median_pause_duration_ms', paraverbal::jsonb -> 'pause_median_ms',
                'pause_time_ratio', paraverbal::jsonb -> 'pause_ratio',
                'f0_median_semitones', CASE
                    WHEN (paraverbal ->> 'f0_median_hz')::double precision > 0
                    THEN to_jsonb(
                        12 * ln((paraverbal ->> 'f0_median_hz')::double precision / 27.5)
                        / ln(2::double precision)
                    )
                    ELSE NULL
                END
            ))
        )::json
        WHERE paraverbal IS NOT NULL
    """))
    op.drop_column("interview_turns", "pyfeat_nonverbal_features")


def downgrade() -> None:
    # This restores the former schema shape. OpenFace observations discarded by
    # upgrade cannot be reconstructed, so the canonical column remains null.
    op.add_column(
        "interview_turns",
        sa.Column("pyfeat_nonverbal_features", sa.JSON(), nullable=True),
    )
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE interview_turns
        SET pyfeat_nonverbal_features = (
            nonverbal_features::jsonb
            - 'median_visual_alignment_dwell_ms'
            - 'mean_smile_activation'
            || jsonb_strip_nulls(jsonb_build_object(
                'visual_alignment_dwell_ms',
                nonverbal_features::jsonb -> 'median_visual_alignment_dwell_ms',
                'smile_intensity_mean',
                nonverbal_features::jsonb -> 'mean_smile_activation'
            ))
        )::json,
        nonverbal_features = NULL
        WHERE nonverbal_features IS NOT NULL
    """))
    connection.execute(sa.text("""
        UPDATE interview_turns
        SET paraverbal = (
            paraverbal::jsonb
            - 'speech_rate_wpm'
            - 'total_pause_duration_ms'
            - 'median_pause_duration_ms'
            - 'pause_time_ratio'
            - 'f0_median_semitones'
            - 'f0_p20_p80_range_semitones'
            - 'median_loudness'
            - 'loudness_p20_p80_range'
            || jsonb_strip_nulls(jsonb_build_object(
                'speaking_rate_wpm', paraverbal::jsonb -> 'speech_rate_wpm',
                'pause_total_ms', paraverbal::jsonb -> 'total_pause_duration_ms',
                'pause_median_ms', paraverbal::jsonb -> 'median_pause_duration_ms',
                'pause_ratio', paraverbal::jsonb -> 'pause_time_ratio',
                'f0_median_hz', CASE
                    WHEN paraverbal::jsonb -> 'f0_median_semitones' IS NOT NULL
                    THEN to_jsonb(
                        27.5 * power(
                            2::double precision,
                            (paraverbal ->> 'f0_median_semitones')::double precision / 12
                        )
                    )
                    ELSE NULL
                END
            ))
        )::json
        WHERE paraverbal IS NOT NULL
    """))
