"""add session binding metadata fields

Revision ID: 20260220_000002
Revises: 20260220_000001
Create Date: 2026-02-20 12:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260220_000002"
down_revision = "20260220_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_tokens", sa.Column("user_agent_hash", sa.String(length=64), nullable=True))
    op.add_column("session_tokens", sa.Column("ip_subnet", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("session_tokens", "ip_subnet")
    op.drop_column("session_tokens", "user_agent_hash")
