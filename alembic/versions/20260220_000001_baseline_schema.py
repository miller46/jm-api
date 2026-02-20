"""baseline schema

Revision ID: 20260220_000001
Revises:
Create Date: 2026-02-20 11:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260220_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("rig_id", sa.String(length=128), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        sa.Column("last_run_log", sa.Text(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("create_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_update_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "session_tokens",
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_jti", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_jti"),
    )
    op.create_index(op.f("ix_session_tokens_expires_at"), "session_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_session_tokens_rotated_from_jti"), "session_tokens", ["rotated_from_jti"], unique=False)
    op.create_index(op.f("ix_session_tokens_user_id"), "session_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_session_tokens_user_id"), table_name="session_tokens")
    op.drop_index(op.f("ix_session_tokens_rotated_from_jti"), table_name="session_tokens")
    op.drop_index(op.f("ix_session_tokens_expires_at"), table_name="session_tokens")
    op.drop_table("session_tokens")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("bots")
