"""Add phase + failure feedback columns to extraction_job.

Revision ID: 20260513_0009
Revises: 20260429_0008
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20260513_0009"
down_revision = "20260429_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extraction_job",
        sa.Column("current_phase", sa.String(80), nullable=True),
    )
    op.add_column(
        "extraction_job",
        sa.Column("current_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "extraction_job",
        sa.Column("failure_phase", sa.String(80), nullable=True),
    )
    op.add_column(
        "extraction_job",
        sa.Column("failure_message_user", sa.Text(), nullable=True),
    )
    op.add_column(
        "extraction_job",
        sa.Column("failure_message_technical", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("extraction_job", "failure_message_technical")
    op.drop_column("extraction_job", "failure_message_user")
    op.drop_column("extraction_job", "failure_phase")
    op.drop_column("extraction_job", "current_message")
    op.drop_column("extraction_job", "current_phase")
