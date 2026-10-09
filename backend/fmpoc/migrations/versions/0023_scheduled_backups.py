"""1.9.0 (#62): scheduled automatic backups - backup_schedule (one row per workspace, created when an Administrator
first saves the settings) and backup_run (history; the files retention may delete). No existing data changes.

Revision ID: 0023_scheduled_backups
Revises: 0022_password_recovery
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_scheduled_backups"
down_revision = "0022_password_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspace.id", name="fk_backup_schedule_workspace_id_workspace"),
                  nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("time_of_day", sa.String(5), nullable=False),
        sa.Column("destination", sa.String(1000), nullable=True),
        sa.Column("keep_daily", sa.Integer(), nullable=False),
        sa.Column("keep_weekly", sa.Integer(), nullable=False),
        sa.Column("keep_monthly", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.String(100), nullable=True),
        sa.Column("wrapped_private_key", sa.Text(), nullable=True),
        sa.Column("key_fingerprint", sa.String(32), nullable=True),
        sa.Column("passphrase_set_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("retry_at", sa.DateTime(), nullable=True),
        sa.Column("retry_wait_minutes", sa.Integer(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("workspace_id", name="uq_backup_schedule_workspace_id"),
    )
    op.create_table(
        "backup_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspace.id", name="fk_backup_run_workspace_id_workspace"),
                  nullable=False),
        sa.Column("trigger", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.String(10), nullable=False),
        sa.Column("destination", sa.String(1000), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("key_fingerprint", sa.String(32), nullable=True),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_reason", sa.String(200), nullable=True),
    )
    op.create_index("ix_backup_run_workspace_id", "backup_run", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_backup_run_workspace_id", table_name="backup_run")
    op.drop_table("backup_run")
    op.drop_table("backup_schedule")
