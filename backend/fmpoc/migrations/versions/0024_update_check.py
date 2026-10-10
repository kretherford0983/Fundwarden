"""1.10.0 (#58): the update notification - update_check (one row: on/off, the last result). No existing data changes;
the check is on until an Administrator turns it off.

Revision ID: 0024_update_check
Revises: 0023_scheduled_backups
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_update_check"
down_revision = "0023_scheduled_backups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "update_check",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channel", sa.String(10), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("update_check")
