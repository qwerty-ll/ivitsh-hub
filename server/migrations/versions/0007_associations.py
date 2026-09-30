"""Associations and memberships; users' contacts (Telegram, VK, Max) and last_seen_at.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('associations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('contacts', sa.String(), nullable=True),
    sa.Column('leader_hint', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_associations_id'), 'associations', ['id'], unique=False)

    op.create_table('memberships',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(), server_default='member', nullable=False),
    sa.Column('status', sa.String(), server_default='pending', nullable=False),
    sa.Column('message', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'association_id', name='uq_membership_user_association')
    )
    op.create_index(op.f('ix_memberships_id'), 'memberships', ['id'], unique=False)
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)
    op.create_index(op.f('ix_memberships_association_id'), 'memberships', ['association_id'], unique=False)

    op.add_column('users', sa.Column('tg_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('vk_url', sa.String(), nullable=True))
    op.add_column('users', sa.Column('max_contact', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('last_seen_at')
        batch_op.drop_column('max_contact')
        batch_op.drop_column('vk_url')
        batch_op.drop_column('tg_username')
    op.drop_index(op.f('ix_memberships_association_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_associations_id'), table_name='associations')
    op.drop_table('associations')
