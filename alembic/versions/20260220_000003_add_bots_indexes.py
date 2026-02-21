"""add indexes for bot list/filter query patterns

Revision ID: 20260220_000003
Revises: 20260220_000002
Create Date: 2026-02-20 21:35:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260220_000003"
down_revision = "20260220_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Single-column indexes for common filter/sort operations.
    op.create_index("ix_bots_rig_id", "bots", ["rig_id"], unique=False)
    op.create_index("ix_bots_kill_switch", "bots", ["kill_switch"], unique=False)
    op.create_index("ix_bots_create_at", "bots", ["create_at"], unique=False)
    op.create_index("ix_bots_last_update_at", "bots", ["last_update_at"], unique=False)
    op.create_index("ix_bots_last_run_at", "bots", ["last_run_at"], unique=False)

    # Composite indexes for common combined filtering/sorting access paths.
    op.create_index(
        "ix_bots_rig_id_kill_switch",
        "bots",
        ["rig_id", "kill_switch"],
        unique=False,
    )
    op.create_index(
        "ix_bots_kill_switch_last_run_at",
        "bots",
        ["kill_switch", "last_run_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bots_kill_switch_last_run_at", table_name="bots")
    op.drop_index("ix_bots_rig_id_kill_switch", table_name="bots")
    op.drop_index("ix_bots_last_run_at", table_name="bots")
    op.drop_index("ix_bots_last_update_at", table_name="bots")
    op.drop_index("ix_bots_create_at", table_name="bots")
    op.drop_index("ix_bots_kill_switch", table_name="bots")
    op.drop_index("ix_bots_rig_id", table_name="bots")
