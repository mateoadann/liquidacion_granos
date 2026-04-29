"""Add forzado_* columns to coe_estado for admin override audit.

Revision ID: 20260429_0008
Revises: 20260427_0007
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "20260429_0008"
down_revision = "20260427_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("coe_estado", sa.Column("forzado_en", sa.DateTime(), nullable=True))
    op.add_column("coe_estado", sa.Column("forzado_por", sa.String(100), nullable=True))
    op.add_column("coe_estado", sa.Column("forzado_razon", sa.Text(), nullable=True))
    op.add_column(
        "coe_estado",
        sa.Column("forzado_estado_previo", sa.String(20), nullable=True),
    )
    op.add_column(
        "coe_estado",
        sa.Column("hash_payload_forzado", sa.String(100), nullable=True),
    )
    op.create_index(
        "idx_coe_estado_forzado_en",
        "coe_estado",
        ["forzado_en"],
    )


def downgrade():
    op.drop_index("idx_coe_estado_forzado_en", table_name="coe_estado")
    op.drop_column("coe_estado", "hash_payload_forzado")
    op.drop_column("coe_estado", "forzado_estado_previo")
    op.drop_column("coe_estado", "forzado_razon")
    op.drop_column("coe_estado", "forzado_por")
    op.drop_column("coe_estado", "forzado_en")
