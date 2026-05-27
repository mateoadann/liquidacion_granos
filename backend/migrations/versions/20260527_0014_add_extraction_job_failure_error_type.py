"""Add failure_error_type column to extraction_job.

The Playwright pipeline classifies failures into types ("auth_failed",
"timeout", "network", "arca_unavailable", "unknown"), but until now that
classification was only used in-memory and never persisted. As a result,
the retry classifier had to default to permissive ("retry anything")
which can lead to auto-retrying auth_failed jobs and locking ARCA accounts.

Revision ID: 20260527_0014
Revises: 20260525_0013
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa


revision = "20260527_0014"
down_revision = "20260525_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extraction_job",
        sa.Column("failure_error_type", sa.String(length=64), nullable=True),
    )


def downgrade():
    op.drop_column("extraction_job", "failure_error_type")
