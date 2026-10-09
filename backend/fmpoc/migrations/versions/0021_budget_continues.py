"""1.8.0 (#89): Historic Budget Traceability - a budget can continue a budget of an earlier Fiscal Year.

Adds budget.continues_budget_id (nullable). Existing budgets are not linked: two budgets with the same code are not
necessarily the same budget, so a Budget Manager links them by hand where wanted. Copies made from now on are linked.

Revision ID: 0021_budget_continues
Revises: 0020_bank_account_balance_history
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_budget_continues"
down_revision = "0020_bank_account_balance_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget", sa.Column("continues_budget_id", sa.Integer(), nullable=True))
    op.create_index("ix_budget_continues_budget_id", "budget", ["continues_budget_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_continues_budget_id", table_name="budget")
    with op.batch_alter_table("budget") as b:
        b.drop_column("continues_budget_id")
