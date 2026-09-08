"""Change interview evaluation scores from a 0-10 scale to a 0-5 scale.

Revision ID: 020_evaluation_scale_five
Revises: 019_public_interview_id
"""

from alembic import op
import sqlalchemy as sa


revision = "020_evaluation_scale_five"
down_revision = "019_public_interview_id"
branch_labels = None
depends_on = None


def _rescale_json_scores(divisor: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE interview_evaluations AS evaluation
            SET evaluation_results = converted.results::json
            FROM (
                SELECT
                    source.id,
                    jsonb_agg(
                        CASE
                            WHEN item.value ? 'score' THEN jsonb_set(
                                item.value,
                                '{{score}}',
                                to_jsonb(round((item.value->>'score')::numeric {divisor}, 1))
                            )
                            ELSE item.value
                        END
                        ORDER BY item.position
                    ) AS results
                FROM interview_evaluations AS source
                CROSS JOIN LATERAL jsonb_array_elements(source.evaluation_results::jsonb)
                    WITH ORDINALITY AS item(value, position)
                GROUP BY source.id
            ) AS converted
            WHERE evaluation.id = converted.id
            """
        )
    )


def upgrade() -> None:
    op.alter_column(
        "interview_evaluations",
        "overall_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        postgresql_using="overall_score::double precision",
    )
    op.execute(
        sa.text(
            """
            UPDATE interview_evaluations
            SET overall_score = round((overall_score::numeric / 2), 1)
            WHERE overall_score IS NOT NULL
            """
        )
    )
    _rescale_json_scores("/ 2")


def downgrade() -> None:
    _rescale_json_scores("* 2")
    op.execute(
        sa.text(
            """
            UPDATE interview_evaluations
            SET overall_score = round(overall_score::numeric * 2)
            WHERE overall_score IS NOT NULL
            """
        )
    )
    op.alter_column(
        "interview_evaluations",
        "overall_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        postgresql_using="overall_score::integer",
    )
