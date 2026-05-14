"""Add scheduler columns to taxpayer.

Revision ID: 20260514_0010
Revises: 20260513_0009
Create Date: 2026-05-14
"""
from alembic import op

revision = "20260514_0010"
down_revision = "20260513_0009"
branch_labels = None
depends_on = None


# IF NOT EXISTS / IF EXISTS guards make this migration safe against a race
# where backend and worker containers both invoke `flask db upgrade` at boot.
def upgrade():
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_activo BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_dias_semana VARCHAR(50) "
        "NOT NULL DEFAULT 'lun,mar,mie,jue,vie'"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_hora_local VARCHAR(5) "
        "NOT NULL DEFAULT '06:00'"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_ultimo_ok TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_ultimo_error TEXT"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "ADD COLUMN IF NOT EXISTS scheduler_ultimo_error_en TIMESTAMP"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_taxpayer_scheduler_activo "
        "ON taxpayer(scheduler_activo)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_taxpayer_scheduler_activo")
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_ultimo_error_en"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_ultimo_error"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_ultimo_ok"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_hora_local"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_dias_semana"
    )
    op.execute(
        "ALTER TABLE taxpayer "
        "DROP COLUMN IF EXISTS scheduler_activo"
    )
