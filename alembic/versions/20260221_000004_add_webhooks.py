"""add webhook subscription and delivery log tables

Revision ID: 20260221_000004
Revises: 20260220_000003
Create Date: 2026-02-21 07:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260221_000004"
down_revision = "20260220_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("target_url", sa.String(length=1024), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_is_active", "webhooks", ["is_active"], unique=False)
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"], unique=False)

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("webhook_id", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_delivery_logs_create_at",
        "webhook_delivery_logs",
        ["create_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_delivery_logs_event_type",
        "webhook_delivery_logs",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_delivery_logs_webhook_id",
        "webhook_delivery_logs",
        ["webhook_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_logs_webhook_id", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_event_type", table_name="webhook_delivery_logs")
    op.drop_index("ix_webhook_delivery_logs_create_at", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")

    op.drop_index("ix_webhooks_user_id", table_name="webhooks")
    op.drop_index("ix_webhooks_is_active", table_name="webhooks")
    op.drop_table("webhooks")
