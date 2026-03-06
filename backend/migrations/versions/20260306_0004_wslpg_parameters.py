"""Create wslpg_parameter table and add datos_limpios to lpg_document

Revision ID: 20260306_0004
Revises: 4029dab0d551
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0004"
down_revision = "4029dab0d551"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wslpg_parameter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tabla", sa.String(60), nullable=False, index=True),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False, server_default=""),
        sa.Column("datos_extra", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tabla", "codigo", name="uq_wslpg_param_tabla_codigo"),
    )

    op.add_column("lpg_document", sa.Column("datos_limpios", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("lpg_document", "datos_limpios")
    op.drop_table("wslpg_parameter")
