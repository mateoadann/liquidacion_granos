"""Seed wslpg_parameter table with AFIP parametric data.

Revision ID: 20260306_0005
Revises: 20260306_0004
Create Date: 2026-03-06
"""
from alembic import op
import json
import os

revision = "20260306_0005"
down_revision = "20260306_0004"
branch_labels = None
depends_on = None

SEED_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wslpg_seed_data.json")


def upgrade():
    # Only seed if table is empty (avoid duplicates on re-run)
    conn = op.get_bind()
    count = conn.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM wslpg_parameter")
    ).scalar()
    if count > 0:
        return

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        rows = json.load(f)

    # Batch insert for performance
    table = __import__("sqlalchemy").table(
        "wslpg_parameter",
        __import__("sqlalchemy").column("tabla"),
        __import__("sqlalchemy").column("codigo"),
        __import__("sqlalchemy").column("descripcion"),
        __import__("sqlalchemy").column("updated_at"),
    )

    now = __import__("datetime").datetime.utcnow()
    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        op.bulk_insert(
            table,
            [
                {
                    "tabla": row["t"],
                    "codigo": row["c"],
                    "descripcion": row["d"],
                    "updated_at": now,
                }
                for row in batch
            ],
        )


def downgrade():
    op.execute("DELETE FROM wslpg_parameter")
