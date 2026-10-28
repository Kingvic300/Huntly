"""remove the X recent-search source

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 17:30:00.000000
"""
from alembic import op


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Jobs already found through X stay; they just lose the link to the removed source.
    op.execute("UPDATE jobs SET source_id = NULL WHERE source_id IN (SELECT id FROM sources WHERE kind = 'x_search')")
    op.execute("DELETE FROM sources WHERE kind = 'x_search'")
    op.execute("DELETE FROM secrets WHERE name = 'x_bearer_token'")


def downgrade() -> None:
    # The deleted sources and the encrypted token cannot be restored.
    pass
