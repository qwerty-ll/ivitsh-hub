"""Calendar: association meetings and attendance, group homework, SDO courses.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('group_homework',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_key', sa.String(), nullable=False),
    sa.Column('group_number', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), server_default='', nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('group_homework', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_group_homework_group_key'), ['group_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_group_homework_id'), ['id'], unique=False)

    op.create_table('meetings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('place', sa.String(), server_default='', nullable=False),
    sa.Column('agenda', sa.Text(), server_default='', nullable=False),
    sa.Column('summary', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meetings_association_id'), ['association_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_starts_at'), ['starts_at'], unique=False)

    op.create_table('sdo_courses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'course_id', name='uq_sdo_course_user')
    )
    with op.batch_alter_table('sdo_courses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sdo_courses_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sdo_courses_user_id'), ['user_id'], unique=False)

    op.create_table('meeting_attendance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meeting_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meeting_id', 'user_id', name='uq_meeting_attendance')
    )
    with op.batch_alter_table('meeting_attendance', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meeting_attendance_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meeting_attendance_meeting_id'), ['meeting_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meeting_attendance_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sdo_synced_at', sa.DateTime(timezone=True), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sdo_synced_at')

    with op.batch_alter_table('meeting_attendance', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meeting_attendance_user_id'))
        batch_op.drop_index(batch_op.f('ix_meeting_attendance_meeting_id'))
        batch_op.drop_index(batch_op.f('ix_meeting_attendance_id'))

    op.drop_table('meeting_attendance')
    with op.batch_alter_table('sdo_courses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sdo_courses_user_id'))
        batch_op.drop_index(batch_op.f('ix_sdo_courses_id'))

    op.drop_table('sdo_courses')
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meetings_starts_at'))
        batch_op.drop_index(batch_op.f('ix_meetings_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_association_id'))

    op.drop_table('meetings')
    with op.batch_alter_table('group_homework', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_group_homework_id'))
        batch_op.drop_index(batch_op.f('ix_group_homework_group_key'))

    op.drop_table('group_homework')
