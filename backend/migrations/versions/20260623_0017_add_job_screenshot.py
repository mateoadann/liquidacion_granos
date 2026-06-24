"""Add job_screenshot table.

Persiste el screenshot de fallo del robot (base64) asociado a un extraction_job,
para mostrarlo en la UI. Tabla aparte para no inflar extraction_job con blobs.

Revision ID: 20260623_0017
Revises: 20260623_0016
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0017"
down_revision = "20260623_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_screenshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("extraction_job_id", sa.Integer(), nullable=False),
        sa.Column("taxpayer_id", sa.Integer(), nullable=True),
        sa.Column("image_base64", sa.Text(), nullable=False),
        sa.Column("fase", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["extraction_job_id"], ["extraction_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["taxpayer_id"], ["taxpayer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_screenshot_extraction_job_id", "job_screenshot", ["extraction_job_id"]
    )
    op.create_index(
        "ix_job_screenshot_created_at", "job_screenshot", ["created_at"]
    )


def downgrade():
    op.drop_index("ix_job_screenshot_created_at", table_name="job_screenshot")
    op.drop_index("ix_job_screenshot_extraction_job_id", table_name="job_screenshot")
    op.drop_table("job_screenshot")
