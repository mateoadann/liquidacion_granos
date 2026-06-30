"""Add control_rpa columns to lpg_document.

Stores the RPA reconciliation verdict (null / ok / inconsistente /
no_encontrado) reported by rpa-holistor, independent from the manual
`controlada` flag. Mismatch detail lives in the carga_inconsistente gestion.

Revision ID: 20260630_0019
Revises: 20260625_0018
Create Date: 2026-06-30
"""
from alembic import op

revision = "20260630_0019"
down_revision = "20260625_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS control_rpa_estado VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE lpg_document "
        "ADD COLUMN IF NOT EXISTS control_rpa_en TIMESTAMP"
    )


def downgrade():
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS control_rpa_en")
    op.execute("ALTER TABLE lpg_document DROP COLUMN IF EXISTS control_rpa_estado")
