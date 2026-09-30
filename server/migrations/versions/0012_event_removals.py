"""People taken off an event's list by its organizers.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('event_removals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('removed_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['removed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'user_id', name='uq_event_removal')
    )
    with op.batch_alter_table('event_removals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_removals_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_removals_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_removals_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('event_removals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_removals_user_id'))
        batch_op.drop_index(batch_op.f('ix_event_removals_id'))
        batch_op.drop_index(batch_op.f('ix_event_removals_event_id'))

    op.drop_table('event_removals')
