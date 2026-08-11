"""Update rude_unfriendly personality with new name and translations

Revision ID: 003_update_rude_unfriendly
Revises: 002_audio_url
Create Date: 2025-11-06 21:35:34.398

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_update_rude_unfriendly'
down_revision = '002_audio_url'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update the rude_unfriendly personality with new name and translations
    op.execute("""
        UPDATE personalities
        SET 
            name = 'Unfriendly person',
            name_translations = '{"es": "Persona poco amigable"}'::jsonb,
            updated_at = NOW()
        WHERE namespace_key = 'rude_unfriendly'
    """)


def downgrade() -> None:
    # Revert to previous values (if known, otherwise leave as is)
    # Note: This downgrade assumes previous values were different
    # If you need to restore specific previous values, update this accordingly
    op.execute("""
        UPDATE personalities
        SET 
            name = 'Rude and unfriendly person',
            name_translations = '{"es": "Persona grosera y poco amigable"}'::jsonb,
            updated_at = NOW()
        WHERE namespace_key = 'rude_unfriendly'
    """)

