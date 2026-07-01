"""Backfill control_rpa_estado for COEs whose carga_inconsistente gestion is
already verified.

Fixes COEs stuck showing a red control check after their carga_inconsistente
gestion was verified: verifying a gestion never cleared
lpg_document.control_rpa_estado, so it stayed 'inconsistente' forever. Sets it
to 'ok' for every COE affected by an already-verified carga_inconsistente
gestion. Idempotent (re-running is a no-op). Data-only, no schema change.

Revision ID: 20260701_0020
Revises: 20260630_0019
Create Date: 2026-07-01
"""
from alembic import op
from sqlalchemy import text

revision = "20260701_0020"
down_revision = "20260630_0019"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(text(
        "SELECT coes_afectados FROM gestiones "
        "WHERE tipo = 'carga_inconsistente' AND estado = 'verificada'"
    )).fetchall()

    coes: set[str] = set()
    for (coes_afectados,) in rows:
        for coe in _as_list(coes_afectados):
            if coe:
                coes.add(str(coe))

    if not coes:
        return

    conn.execute(
        text(
            "UPDATE lpg_document SET control_rpa_estado = 'ok' "
            "WHERE control_rpa_estado = 'inconsistente' AND coe IN :coes"
        ).bindparams(coes=tuple(coes)),
    )


def downgrade():
    # No-op: we cannot distinguish backfilled 'ok' from RPA-reported 'ok'.
    pass


def _as_list(value):
    """coes_afectados is JSON; Postgres returns a list, SQLite returns a str."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []
