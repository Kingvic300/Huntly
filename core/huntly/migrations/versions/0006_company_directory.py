"""company directory

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=24), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=16), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('open_jobs', sa.Integer(), nullable=False),
        sa.Column('jobs_found', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform', 'slug', name='uq_companies_board'),
    )
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_companies_last_checked_at'), ['last_checked_at'], unique=False)
    op.create_table(
        'company_probes',
        sa.Column('name_key', sa.String(length=120), nullable=False),
        sa.Column('probed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('found', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('name_key'),
    )


def downgrade() -> None:
    op.drop_table('company_probes')
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companies_last_checked_at'))
    op.drop_table('companies')
