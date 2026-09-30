"""Events: registrations, feedback, documents; manual achievements for the ПГАС summary.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scope', sa.String(), server_default='association', nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('place', sa.String(), server_default='', nullable=False),
    sa.Column('participant_limit', sa.Integer(), nullable=True),
    sa.Column('volunteer_limit', sa.Integer(), nullable=True),
    sa.Column('registration_open', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_events_association_id'), ['association_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_starts_at'), ['starts_at'], unique=False)

    op.create_table('manual_achievements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('organizer', sa.String(), server_default='', nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('role', sa.String(), server_default='', nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('manual_achievements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_manual_achievements_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_manual_achievements_user_id'), ['user_id'], unique=False)

    op.create_table('event_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'user_id', name='uq_event_feedback')
    )
    with op.batch_alter_table('event_feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_feedback_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_feedback_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_feedback_user_id'), ['user_id'], unique=False)

    op.create_table('event_registrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(), server_default='participant', nullable=False),
    sa.Column('source', sa.String(), server_default='self', nullable=False),
    sa.Column('attended', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'user_id', name='uq_event_registration')
    )
    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_registrations_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_registrations_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_registrations_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('event_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('achievement_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_attachments_achievement_id'), ['achievement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attachments_event_id'), ['event_id'], unique=False)
        batch_op.create_foreign_key('fk_attachments_event_id', 'events', ['event_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_attachments_achievement_id', 'manual_achievements', ['achievement_id'], ['id'], ondelete='CASCADE')



def downgrade() -> None:
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attachments_event_id'))
        batch_op.drop_index(batch_op.f('ix_attachments_achievement_id'))
        batch_op.drop_column('achievement_id')
        batch_op.drop_column('event_id')

    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_registrations_user_id'))
        batch_op.drop_index(batch_op.f('ix_event_registrations_id'))
        batch_op.drop_index(batch_op.f('ix_event_registrations_event_id'))

    op.drop_table('event_registrations')
    with op.batch_alter_table('event_feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_feedback_user_id'))
        batch_op.drop_index(batch_op.f('ix_event_feedback_id'))
        batch_op.drop_index(batch_op.f('ix_event_feedback_event_id'))

    op.drop_table('event_feedback')
    with op.batch_alter_table('manual_achievements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_manual_achievements_user_id'))
        batch_op.drop_index(batch_op.f('ix_manual_achievements_id'))

    op.drop_table('manual_achievements')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_starts_at'))
        batch_op.drop_index(batch_op.f('ix_events_id'))
        batch_op.drop_index(batch_op.f('ix_events_association_id'))

    op.drop_table('events')
