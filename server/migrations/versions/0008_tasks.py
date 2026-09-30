"""Tasks (association and personal), assignees, comments, association announcements, attachments.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('association_posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('text', sa.Text(), server_default='', nullable=False),
    sa.Column('to_all', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('association_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_association_posts_association_id'), ['association_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_association_posts_id'), ['id'], unique=False)

    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('association_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('color', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['association_id'], ['associations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_association_id'), ['association_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_created_by_id'), ['created_by_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_id'), ['id'], unique=False)

    op.create_table('association_post_recipients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['association_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('post_id', 'user_id', name='uq_post_recipient')
    )
    with op.batch_alter_table('association_post_recipients', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_association_post_recipients_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_association_post_recipients_post_id'), ['post_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_association_post_recipients_user_id'), ['user_id'], unique=False)

    op.create_table('attachments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=True),
    sa.Column('post_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('stored_name', sa.String(), nullable=True),
    sa.Column('size', sa.Integer(), nullable=True),
    sa.Column('content_type', sa.String(), nullable=True),
    sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['post_id'], ['association_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attachments_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attachments_post_id'), ['post_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attachments_task_id'), ['task_id'], unique=False)

    op.create_table('task_assignees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), server_default='todo', nullable=False),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'user_id', name='uq_task_assignee')
    )
    with op.batch_alter_table('task_assignees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_assignees_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_assignees_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_assignees_user_id'), ['user_id'], unique=False)

    op.create_table('task_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('task_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_comments_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_comments_task_id'), ['task_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('task_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_comments_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_comments_id'))

    op.drop_table('task_comments')
    with op.batch_alter_table('task_assignees', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_assignees_user_id'))
        batch_op.drop_index(batch_op.f('ix_task_assignees_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_assignees_id'))

    op.drop_table('task_assignees')
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attachments_task_id'))
        batch_op.drop_index(batch_op.f('ix_attachments_post_id'))
        batch_op.drop_index(batch_op.f('ix_attachments_id'))

    op.drop_table('attachments')
    with op.batch_alter_table('association_post_recipients', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_association_post_recipients_user_id'))
        batch_op.drop_index(batch_op.f('ix_association_post_recipients_post_id'))
        batch_op.drop_index(batch_op.f('ix_association_post_recipients_id'))

    op.drop_table('association_post_recipients')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_created_by_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_association_id'))

    op.drop_table('tasks')
    with op.batch_alter_table('association_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_association_posts_id'))
        batch_op.drop_index(batch_op.f('ix_association_posts_association_id'))

    op.drop_table('association_posts')
