"""Bookings of coworking room 108 and laptops.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resource', sa.String(), nullable=False),
    sa.Column('zone', sa.String(), nullable=True),
    sa.Column('laptops', sa.Integer(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('purpose', sa.String(), server_default='', nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=True),
    sa.Column('booked_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by_id', sa.Integer(), nullable=True),
    sa.Column('cancel_reason', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['booked_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cancelled_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bookings_association_id'), ['association_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_booked_by_id'), ['booked_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_ends_at'), ['ends_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_starts_at'), ['starts_at'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_starts_at'))
        batch_op.drop_index(batch_op.f('ix_bookings_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_ends_at'))
        batch_op.drop_index(batch_op.f('ix_bookings_booked_by_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_association_id'))

    op.drop_table('bookings')
