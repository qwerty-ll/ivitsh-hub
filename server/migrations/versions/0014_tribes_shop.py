"""Tribe tournaments, bits grants, the merch shop.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('shop_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('kind', sa.String(), server_default='merch', nullable=False),
    sa.Column('price', sa.Integer(), nullable=False),
    sa.Column('stock', sa.Integer(), nullable=True),
    sa.Column('per_user_limit', sa.Integer(), nullable=True),
    sa.Column('image_name', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('sort', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('shop_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_items_id'), ['id'], unique=False)

    op.create_table('shop_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=True),
    sa.Column('item_title', sa.String(), nullable=False),
    sa.Column('price', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), server_default='new', nullable=False),
    sa.Column('comment', sa.String(), nullable=True),
    sa.Column('handled_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['handled_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['shop_items.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('shop_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shop_orders_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_orders_item_id'), ['item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shop_orders_user_id'), ['user_id'], unique=False)

    op.create_table('tournaments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(), server_default='draft', nullable=False),
    sa.Column('groups', sa.Text(), server_default='', nullable=False),
    sa.Column('auto_join', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('prize_1', sa.Integer(), server_default='50', nullable=False),
    sa.Column('prize_2', sa.Integer(), server_default='30', nullable=False),
    sa.Column('prize_3', sa.Integer(), server_default='15', nullable=False),
    sa.Column('winner_tribe_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tournaments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tournaments_id'), ['id'], unique=False)

    op.create_table('bits_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('tournament_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bits_grants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bits_grants_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bits_grants_user_id'), ['user_id'], unique=False)

    op.create_table('tribes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tournament_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('color', sa.String(), nullable=False),
    sa.Column('final_points', sa.Integer(), nullable=True),
    sa.Column('place', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tribes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tribes_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tribes_tournament_id'), ['tournament_id'], unique=False)

    op.create_table('tribe_awards',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tribe_id', sa.Integer(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tribe_id'], ['tribes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tribe_awards', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tribe_awards_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tribe_awards_tribe_id'), ['tribe_id'], unique=False)

    op.create_table('tribe_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tournament_id', sa.Integer(), nullable=False),
    sa.Column('tribe_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['tournament_id'], ['tournaments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tribe_id'], ['tribes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tournament_id', 'user_id', name='uq_tribe_member')
    )
    with op.batch_alter_table('tribe_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tribe_members_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tribe_members_tournament_id'), ['tournament_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tribe_members_tribe_id'), ['tribe_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tribe_members_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('tribe_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tribe_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_tribe_members_tribe_id'))
        batch_op.drop_index(batch_op.f('ix_tribe_members_tournament_id'))
        batch_op.drop_index(batch_op.f('ix_tribe_members_id'))

    op.drop_table('tribe_members')
    with op.batch_alter_table('tribe_awards', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tribe_awards_tribe_id'))
        batch_op.drop_index(batch_op.f('ix_tribe_awards_id'))

    op.drop_table('tribe_awards')
    with op.batch_alter_table('tribes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tribes_tournament_id'))
        batch_op.drop_index(batch_op.f('ix_tribes_id'))

    op.drop_table('tribes')
    with op.batch_alter_table('bits_grants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bits_grants_user_id'))
        batch_op.drop_index(batch_op.f('ix_bits_grants_id'))

    op.drop_table('bits_grants')
    with op.batch_alter_table('tournaments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tournaments_id'))

    op.drop_table('tournaments')
    with op.batch_alter_table('shop_orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shop_orders_user_id'))
        batch_op.drop_index(batch_op.f('ix_shop_orders_item_id'))
        batch_op.drop_index(batch_op.f('ix_shop_orders_id'))

    op.drop_table('shop_orders')
    with op.batch_alter_table('shop_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shop_items_id'))

    op.drop_table('shop_items')
