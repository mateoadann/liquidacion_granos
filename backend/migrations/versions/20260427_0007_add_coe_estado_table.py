"""Add coe_estado table for tracking COE lifecycle state.

Revision ID: 20260427_0007
Revises: 20260422_0006
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260427_0007"
down_revision = "20260422_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coe_estado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coe", sa.String(20), nullable=False),
        sa.Column(
            "lpg_document_id",
            sa.Integer(),
            sa.ForeignKey("lpg_document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cuit_empresa", sa.String(11), nullable=False),
        sa.Column("cuit_comprador", sa.String(11), nullable=True),
        sa.Column("codigo_comprobante", sa.String(10), nullable=True),
        sa.Column("tipo_pto_vta", sa.Integer(), nullable=True),
        sa.Column("nro_comprobante", sa.Integer(), nullable=True),
        sa.Column("fecha_emision", sa.String(20), nullable=True),
        sa.Column("id_liquidacion", sa.String(50), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("descargado_en", sa.DateTime(), nullable=True),
        sa.Column("cargado_en", sa.DateTime(), nullable=True),
        sa.Column("error_mensaje", sa.Text(), nullable=True),
        sa.Column("error_fase", sa.String(20), nullable=True),
        sa.Column("ultima_ejecucion_id", sa.String(50), nullable=True),
        sa.Column("ultimo_usuario", sa.String(100), nullable=True),
        sa.Column("hash_payload_emitido", sa.String(100), nullable=True),
        sa.Column("hash_payload_cargado", sa.String(100), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_coe_estado_coe", "coe_estado", ["coe"], unique=True)
    op.create_index(
        "ix_coe_estado_lpg_document_id",
        "coe_estado",
        ["lpg_document_id"],
        unique=True,
    )
    op.create_index(
        "ix_coe_estado_id_liquidacion",
        "coe_estado",
        ["id_liquidacion"],
        unique=True,
    )
    op.create_index(
        "idx_coe_estado_empresa_estado",
        "coe_estado",
        ["cuit_empresa", "estado"],
    )


def downgrade():
    op.drop_index("idx_coe_estado_empresa_estado", table_name="coe_estado")
    op.drop_index("ix_coe_estado_id_liquidacion", table_name="coe_estado")
    op.drop_index("ix_coe_estado_lpg_document_id", table_name="coe_estado")
    op.drop_index("ix_coe_estado_coe", table_name="coe_estado")
    op.drop_table("coe_estado")
