"""Archive of finished task cards and of tasks leaders set.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('task_assignees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('archived_at')

    with op.batch_alter_table('task_assignees', schema=None) as batch_op:
        batch_op.drop_column('archived_at')

