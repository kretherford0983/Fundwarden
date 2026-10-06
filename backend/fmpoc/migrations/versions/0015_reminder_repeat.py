"""1.6.7: organization reminders can repeat (every N days / weeks / months / years, optionally until a date).

Additive only - nullable columns (repeat_index defaults to 0) and one index. Existing reminders stay one-time.

Revision ID: 0015_reminder_repeat
Revises: 0014_entity_position
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_reminder_repeat"
down_revision = "0014_entity_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminder", sa.Column("repeat_every", sa.Integer(), nullable=True))
    op.add_column("reminder", sa.Column("repeat_unit", sa.String(8), nullable=True))
    op.add_column("reminder", sa.Column("repeat_until", sa.Date(), nullable=True))
    op.add_column("reminder", sa.Column("repeat_anchor", sa.Date(), nullable=True))
    op.add_column("reminder", sa.Column("repeat_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reminder", sa.Column("repeat_source_id", sa.Integer(), nullable=True))
    op.create_index("ix_reminder_repeat_source_id", "reminder", ["repeat_source_id"])


def downgrade() -> None:
    op.drop_index("ix_reminder_repeat_source_id", table_name="reminder")
    with op.batch_alter_table("reminder") as b:
        for col in ("repeat_source_id", "repeat_index", "repeat_anchor", "repeat_until", "repeat_unit", "repeat_every"):
            b.drop_column(col)
