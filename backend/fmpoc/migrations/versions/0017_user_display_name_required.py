"""1.7.1 (#47): every user has a display name of at least 3 characters.

1. Existing users without a display name, or with one shorter than 3 characters after trimming, get their username
   as display name (usernames are 3-64 characters, so the copied value always meets the rule). Every other display
   name is left exactly as it is.
2. The rule is enforced in the database by two triggers on app_user (insert, and update of display_name). Triggers
   are used instead of NOT NULL + CHECK on the column because SQLite can only add those by rebuilding the table, and
   app_user is referenced by almost every other table. NOTE for later migrations: a batch operation that rebuilds
   app_user drops its triggers - recreate them (tests/test_v171_display_name.py checks that they exist at head).

No column is added or removed.

Revision ID: 0017_user_display_name_required
Revises: 0016_entity_phone_format
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_user_display_name_required"
down_revision = "0016_entity_phone_format"
branch_labels = None
depends_on = None

_RULE = "NEW.display_name IS NULL OR length(trim(NEW.display_name)) < 3"
_MESSAGE = "a user needs a display name of at least 3 characters"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE app_user SET display_name = username "
        "WHERE display_name IS NULL OR length(trim(display_name)) < 3"))
    op.execute(f"""
        CREATE TRIGGER app_user_display_name_insert BEFORE INSERT ON app_user
        WHEN {_RULE}
        BEGIN SELECT RAISE(ABORT, '{_MESSAGE}'); END;
    """)
    op.execute(f"""
        CREATE TRIGGER app_user_display_name_update BEFORE UPDATE OF display_name ON app_user
        WHEN {_RULE}
        BEGIN SELECT RAISE(ABORT, '{_MESSAGE}'); END;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS app_user_display_name_insert")
    op.execute("DROP TRIGGER IF EXISTS app_user_display_name_update")
