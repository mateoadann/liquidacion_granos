"""Add failure_code column to extraction_job.

map_failure now returns a stable code (AUTH_FAILED, SERVICE_NOT_ADHERED, etc.)
used by the extraction-health panel to classify clients into a traffic-light
state. Persisting the code as its own column avoids parsing the technical
message string. Old jobs have NULL and are shown as "unknown/grey".

Revision ID: 20260623_0015
Revises: 20260527_0014
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0015"
down_revision = "20260527_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extraction_job",
        sa.Column("failure_code", sa.String(length=40), nullable=True),
    )


def downgrade():
    op.drop_column("extraction_job", "failure_code")
