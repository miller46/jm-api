"""add background tasks table

Revision ID: 20260223_000005
Revises: 20260221_000004
Create Date: 2026-02-23 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260223_000005"
down_revision = "20260221_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_type", "tasks", ["type"], unique=False)
    op.create_index("ix_tasks_create_at", "tasks", ["create_at"], unique=False)
    op.create_index("ix_tasks_status_create_at", "tasks", ["status", "create_at"], unique=False)
    op.create_index("ix_tasks_processing_started_at", "tasks", ["processing_started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_processing_started_at", table_name="tasks")
    op.drop_index("ix_tasks_status_create_at", table_name="tasks")
    op.drop_index("ix_tasks_create_at", table_name="tasks")
    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")
