"""Add controlada columns to lpg_document.

Adds per-COE locally-audited flag with actor attribution and timestamp.

Revision ID: 20260522_0012
Revises: 20260515_0011
Create Date: 2026-05-22
"""
from alembic import op

revision = "20260522_0012"
down_revision = "20260515_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS controlada BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS controlada_por VARCHAR(80)"
    )
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS controlada_por_nombre VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS controlada_en TIMESTAMP"
    )


def downgrade():
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS controlada_en")
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS controlada_por_nombre")
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS controlada_por")
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS controlada")
