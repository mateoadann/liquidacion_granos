"""Add pdf_cache table.

Revision ID: 20260422_0006
Revises: 20260306_0005
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260422_0006"
down_revision = "20260306_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pdf_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lpg_document_id", sa.Integer(), nullable=False),
        sa.Column("pdf_base64", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lpg_document_id"],
            ["lpg_document.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lpg_document_id"),
    )


def downgrade():
    op.drop_table("pdf_cache")
