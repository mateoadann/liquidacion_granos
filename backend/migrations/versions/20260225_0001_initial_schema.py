"""Initial schema

Revision ID: 20260225_0001
Revises:
Create Date: 2026-02-25 18:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260225_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "taxpayer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cuit", sa.String(length=11), nullable=False),
        sa.Column("razon_social", sa.String(length=255), nullable=True),
        sa.Column(
            "ambiente", sa.String(length=20), nullable=False, server_default="homologacion"
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuit"),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taxpayer_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=True),
        sa.Column("code", sa.String(length=30), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("request_xml", sa.Text(), nullable=True),
        sa.Column("response_xml", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["taxpayer_id"], ["taxpayer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "extraction_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taxpayer_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["taxpayer_id"], ["taxpayer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lpg_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taxpayer_id", sa.Integer(), nullable=False),
        sa.Column("coe", sa.String(length=20), nullable=True),
        sa.Column("pto_emision", sa.Integer(), nullable=True),
        sa.Column("nro_orden", sa.BigInteger(), nullable=True),
        sa.Column("estado", sa.String(length=10), nullable=True),
        sa.Column("tipo_documento", sa.String(length=30), nullable=False, server_default="LPG"),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["taxpayer_id"], ["taxpayer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lpg_document_coe"), "lpg_document", ["coe"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_lpg_document_coe"), table_name="lpg_document")
    op.drop_table("lpg_document")
    op.drop_table("extraction_job")
    op.drop_table("audit_event")
    op.drop_table("taxpayer")
