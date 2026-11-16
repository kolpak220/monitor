"""Initial monitoring schema.

Revision ID: 20261116_0001
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False, server_default="both"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("username", name="uq_targets_username"),
    )
    op.create_index("ix_targets_username", "targets", ["username"], unique=False)
    op.create_index("ix_targets_next_check_at", "targets", ["next_check_at"], unique=False)

    op.create_table(
        "check_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=100), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_check_results_target_id", "check_results", ["target_id"], unique=False)
    op.create_index(
        "ix_check_results_target_checked",
        "check_results",
        ["target_id", "checked_at"],
        unique=False,
    )

    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.String(length=32), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.String(length=255), nullable=False, server_default=""),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notifications_target_id", "notifications", ["target_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_target_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("service_heartbeats")
    op.drop_index("ix_check_results_target_checked", table_name="check_results")
    op.drop_index("ix_check_results_target_id", table_name="check_results")
    op.drop_table("check_results")
    op.drop_index("ix_targets_next_check_at", table_name="targets")
    op.drop_index("ix_targets_username", table_name="targets")
    op.drop_table("targets")
