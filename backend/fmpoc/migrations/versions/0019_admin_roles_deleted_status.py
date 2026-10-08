"""1.7.3 (#52, #53): Budget Admin and Register Admin roles; budgets and transactions can be marked Deleted.

- Adds the two roles to the role table (new installations get them from the role list at initialization).
- register_transaction gains deleted_at, deleted_by_user_id and delete_reason. A deleted budget keeps its reason in
  the existing status_reason column. Status values are plain strings, so "DELETED" needs no schema change.
Nothing existing changes.

Revision ID: 0019_admin_roles_deleted_status
Revises: 0018_bank_account_sort_order
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_admin_roles_deleted_status"
down_revision = "0018_bank_account_sort_order"
branch_labels = None
depends_on = None

ROLES = [("BUDGET_ADMIN", "Budget Admin", "FINANCIAL"), ("REGISTER_ADMIN", "Register Admin", "FINANCIAL")]


def upgrade() -> None:
    op.add_column("register_transaction", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("register_transaction", sa.Column("deleted_by_user_id", sa.Integer(), nullable=True))
    op.add_column("register_transaction", sa.Column("delete_reason", sa.String(1000), nullable=True))
    bind = op.get_bind()
    have = {r[0] for r in bind.execute(sa.text("SELECT code FROM role")).fetchall()}
    for code, name, domain in ROLES:
        if code not in have:
            bind.execute(sa.text("INSERT INTO role (code, name, security_domain) VALUES (:c, :n, :d)"),
                         {"c": code, "n": name, "d": domain})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM user_role WHERE role_id IN (SELECT id FROM role WHERE code IN "
                         "('BUDGET_ADMIN', 'REGISTER_ADMIN'))"))
    bind.execute(sa.text("DELETE FROM role WHERE code IN ('BUDGET_ADMIN', 'REGISTER_ADMIN')"))
    with op.batch_alter_table("register_transaction") as b:
        for col in ("delete_reason", "deleted_by_user_id", "deleted_at"):
            b.drop_column(col)
