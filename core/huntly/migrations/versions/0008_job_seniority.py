"""job seniority level

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from huntly.services.matching import seniority_level


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('seniority', sa.String(length=16), nullable=True))
        batch_op.create_index(batch_op.f('ix_jobs_seniority'), ['seniority'], unique=False)
    # Saved jobs get a level from their title and description; new jobs also use the platform's label.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, title, substr(description, 1, 6000) FROM jobs")).fetchall()
    for job_id, title, description in rows:
        level = seniority_level(title or "", description or "")
        if level:
            conn.execute(sa.text("UPDATE jobs SET seniority = :level WHERE id = :id"), {"level": level, "id": job_id})


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_seniority'))
        batch_op.drop_column('seniority')
