"""Journal of administrators' actions; the unused "curator" role becomes "student".

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_name', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_user_id', sa.Integer(), nullable=True),
        sa.Column('target_name', sa.String(), nullable=True),
        sa.Column('details', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_actions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_admin_actions_actor_id'), ['actor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_admin_actions_target_user_id'), ['target_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_admin_actions_created_at'), ['created_at'], unique=False)

    # "curator" was never given any rights
    op.execute("UPDATE users SET role = 'student' WHERE role = 'curator'")


def downgrade() -> None:
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_actions_created_at'))
        batch_op.drop_index(batch_op.f('ix_admin_actions_target_user_id'))
        batch_op.drop_index(batch_op.f('ix_admin_actions_actor_id'))
        batch_op.drop_index(batch_op.f('ix_admin_actions_id'))
    op.drop_table('admin_actions')
