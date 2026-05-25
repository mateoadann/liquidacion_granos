"""Move uniqueness from cuit to cuit_representado on taxpayer.

A single CUIT (the represented taxpayer's broker/operator) may legitimately
appear in multiple rows, each acting on behalf of a different represented
taxpayer (cuit_representado). What MUST be unique is cuit_representado:
the same represented party cannot exist twice in the system.

Revision ID: 20260525_0013
Revises: 20260522_0012
Create Date: 2026-05-25
"""
from alembic import op


revision = "20260525_0013"
down_revision = "20260522_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE taxpayer DROP CONSTRAINT IF EXISTS taxpayer_cuit_key")
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD CONSTRAINT taxpayer_cuit_representado_key UNIQUE (cuit_representado)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE taxpayer DROP CONSTRAINT IF EXISTS taxpayer_cuit_representado_key"
    )
    op.execute("ALTER TABLE taxpayer ADD CONSTRAINT taxpayer_cuit_key UNIQUE (cuit)")
