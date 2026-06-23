"""Add auth-block fields to taxpayer.

clave_fiscal_actualizada_en: timestamp del último cambio de la clave fiscal,
para reactivar el scheduler solo cuando la credencial se actualizó.
scheduler_pausado_por_auth: distingue pausa automática por AUTH_FAILED
(auto-reactivable) de pausa manual.

Revision ID: 20260623_0016
Revises: 20260623_0015
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0016"
down_revision = "20260623_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "taxpayer",
        sa.Column("clave_fiscal_actualizada_en", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "taxpayer",
        sa.Column(
            "scheduler_pausado_por_auth",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("taxpayer", "scheduler_pausado_por_auth")
    op.drop_column("taxpayer", "clave_fiscal_actualizada_en")
