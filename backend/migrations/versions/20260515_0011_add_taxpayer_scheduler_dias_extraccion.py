"""Add scheduler_dias_extraccion to taxpayer.

Configurable per taxpayer: how many days back to scrape from Arca on
each scheduled run. Default 90 — matches old hardcoded default.

Revision ID: 20260515_0011
Revises: 20260514_0010
Create Date: 2026-05-15
"""
from alembic import op

revision = "20260515_0011"
down_revision = "20260514_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_dias_extraccion INTEGER "
        "NOT NULL DEFAULT 90"
    )


def downgrade():
    op.execute("ALTER TABLE taxpayer DROP COLUMN IF EXISTS scheduler_dias_extraccion")
