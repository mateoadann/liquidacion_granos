"""add gestiones table (SPEC §8.1 — gestiones de datos faltantes)

Revision ID: 20260625_0018
Revises: 20260623_0017
Create Date: 2026-06-25
"""
import sqlalchemy as sa
from alembic import op

revision = "20260625_0018"
down_revision = "20260623_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gestiones",
        sa.Column("gestion_id", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("cuit_empresa", sa.Text(), nullable=False),
        sa.Column("razon_social", sa.Text(), nullable=True),
        sa.Column("identificador", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("datos_contexto", sa.JSON(), nullable=True),
        sa.Column("coes_afectados", sa.JSON(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("detectado_en", sa.Text(), nullable=False),
        sa.Column("realizada_en", sa.Text(), nullable=True),
        sa.Column("realizada_por", sa.Text(), nullable=True),
        sa.Column("verificada_en", sa.Text(), nullable=True),
        sa.Column("verificacion_detalle", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("gestion_id"),
    )
    op.create_index(
        "idx_gestiones_empresa_estado", "gestiones", ["cuit_empresa", "estado"]
    )
    op.create_index("idx_gestiones_estado", "gestiones", ["estado"])


def downgrade():
    op.drop_index("idx_gestiones_estado", table_name="gestiones")
    op.drop_index("idx_gestiones_empresa_estado", table_name="gestiones")
    op.drop_table("gestiones")
