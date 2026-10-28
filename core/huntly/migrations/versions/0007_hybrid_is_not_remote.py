"""hybrid jobs are not remote

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28 19:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from huntly.services.sources.base import is_hybrid


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-check jobs already saved as remote with the hybrid rule new jobs now go through.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, title, location, substr(description, 1, 4000) FROM jobs WHERE remote = 1")).fetchall()
    hybrid = [r[0] for r in rows if is_hybrid(r[1] or "", r[2] or "", r[3] or "")]
    for job_id in hybrid:
        conn.execute(sa.text("UPDATE jobs SET remote = 0 WHERE id = :id"), {"id": job_id})


def downgrade() -> None:
    # Which jobs were changed is not recorded; they stay not remote.
    pass
