"""1.8.0 (#113): forgotten password - security questions, persistent escalating lock-out, notices.

Adds to app_user: failed_attempts (0), locked_until, must_change_password (false), reset_question_slot,
reset_question_at, notice_failed_attempts_at, notice_password_reset_at, notice_password_reset_method. Creates
user_security_question and security_notice. No existing data changes; every user sets up security questions at the
next sign-in.

Revision ID: 0022_password_recovery
Revises: 0021_budget_continues
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_password_recovery"
down_revision = "0021_budget_continues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ADD COLUMN (no batch): a batch operation would rebuild app_user and drop the display-name triggers of
    # migration 0017. SQLite adds NOT NULL columns with a constant default in place.
    op.add_column("app_user", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_user", sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.add_column("app_user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_user", sa.Column("reset_question_slot", sa.Integer(), nullable=True))
    op.add_column("app_user", sa.Column("reset_question_at", sa.DateTime(), nullable=True))
    op.add_column("app_user", sa.Column("notice_failed_attempts_at", sa.DateTime(), nullable=True))
    op.add_column("app_user", sa.Column("notice_password_reset_at", sa.DateTime(), nullable=True))
    op.add_column("app_user", sa.Column("notice_password_reset_method", sa.String(30), nullable=True))
    op.create_table(
        "user_security_question",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", name="fk_user_security_question_user_id_app_user"),
                  nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("question_code", sa.String(40), nullable=False),
        sa.Column("answer_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "slot", name="uq_user_security_question_slot"),
    )
    op.create_index("ix_user_security_question_user_id", "user_security_question", ["user_id"])
    op.create_table(
        "security_notice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspace.id", name="fk_security_notice_workspace_id_workspace"),
                  nullable=False),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_security_notice_workspace_id", "security_notice", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_security_notice_workspace_id", table_name="security_notice")
    op.drop_table("security_notice")
    op.drop_index("ix_user_security_question_user_id", table_name="user_security_question")
    op.drop_table("user_security_question")
    for c in ("notice_password_reset_method", "notice_password_reset_at", "notice_failed_attempts_at",
              "reset_question_at", "reset_question_slot", "must_change_password", "locked_until", "failed_attempts"):
        op.drop_column("app_user", c)   # SQLite 3.35+: in place, the 0017 triggers stay
