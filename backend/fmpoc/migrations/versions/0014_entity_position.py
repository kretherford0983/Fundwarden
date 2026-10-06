"""1.6.7: an individual Entity can carry a position in the organization (e.g. "Treasurer"), offered as the signer's
title on the audit review signature page and the cash count sheet.

Additive only - one nullable column.

Revision ID: 0014_entity_position
Revises: 0013_fundraiser_cancel
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_entity_position"
down_revision = "0013_fundraiser_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entity", sa.Column("position", sa.String(60), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("entity") as b:
        b.drop_column("position")
