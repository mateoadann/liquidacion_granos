"""Add phase + failure feedback columns to extraction_job.

Revision ID: 20260513_0009
Revises: 20260429_0008
Create Date: 2026-05-13
"""
from alembic import op

revision = "20260513_0009"
down_revision = "20260429_0008"
branch_labels = None
depends_on = None


# IF NOT EXISTS / IF EXISTS guards make this migration safe against a race
# where backend and worker containers both invoke `flask db upgrade` at boot.
def upgrade():
    op.execute(
        "ALTER TABLE extraction_job "
        "ADD COLUMN IF NOT EXISTS current_phase VARCHAR(80)"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "ADD COLUMN IF NOT EXISTS current_message TEXT"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "ADD COLUMN IF NOT EXISTS failure_phase VARCHAR(80)"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "ADD COLUMN IF NOT EXISTS failure_message_user TEXT"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "ADD COLUMN IF NOT EXISTS failure_message_technical TEXT"
    )


def downgrade():
    op.execute(
        "ALTER TABLE extraction_job "
        "DROP COLUMN IF EXISTS failure_message_technical"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "DROP COLUMN IF EXISTS failure_message_user"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "DROP COLUMN IF EXISTS failure_phase"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "DROP COLUMN IF EXISTS current_message"
    )
    op.execute(
        "ALTER TABLE extraction_job "
        "DROP COLUMN IF EXISTS current_phase"
    )
