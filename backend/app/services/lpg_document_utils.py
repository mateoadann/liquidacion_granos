"""Shared helpers for extracting data from LpgDocument instances.

Centralises logic that was previously duplicated across API modules
(clients.py, coes.py) so that changes only need to happen in one place.
"""
from __future__ import annotations

from sqlalchemy import cast, Date, literal_column, text
from sqlalchemy.sql.expression import ClauseElement, ColumnElement, TextClause

from ..extensions import db
from ..models import LpgDocument


def extract_fecha_liquidacion(doc: LpgDocument) -> str | None:
    """Extract fechaLiquidacion from datos_limpios (preferred) or raw_data.

    For AJUSTE documents, fechaLiquidacion lives inside
    raw_data.data.ajusteUnificado.ajusteCredito/ajusteDebito.
    datos_limpios stores it as credito_fechaLiquidacion / debito_fechaLiquidacion,
    and (after rebuild) also at the root level as fechaLiquidacion.
    """
    dl = doc.datos_limpios or {}

    # 1) nivel raíz de datos_limpios (funciona para LPG y ajustes reconstruidos)
    if dl.get("fechaLiquidacion"):
        return str(dl["fechaLiquidacion"])

    # 2) fallback ajuste: datos_limpios con prefijo credito/debito
    if dl.get("credito_fechaLiquidacion"):
        return str(dl["credito_fechaLiquidacion"])
    if dl.get("debito_fechaLiquidacion"):
        return str(dl["debito_fechaLiquidacion"])

    # 3) fallback raw_data nivel raíz (LPG sin datos_limpios)
    raw = doc.raw_data or {}
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    if isinstance(data, dict):
        if data.get("fechaLiquidacion"):
            return str(data["fechaLiquidacion"])
        # 4) fallback raw_data ajuste
        ajuste = data.get("ajusteUnificado", {})
        if isinstance(ajuste, dict):
            credito = ajuste.get("ajusteCredito", {})
            if isinstance(credito, dict) and credito.get("fechaLiquidacion"):
                return str(credito["fechaLiquidacion"])
            debito = ajuste.get("ajusteDebito", {})
            if isinstance(debito, dict) and debito.get("fechaLiquidacion"):
                return str(debito["fechaLiquidacion"])
    return None


def _is_sqlite() -> bool:
    """Return True when the current engine is SQLite."""
    return db.engine.dialect.name == "sqlite"


def fecha_liquidacion_expr() -> TextClause:
    """Return a SQL COALESCE expression over datos_limpios JSON fields.

    Covers both LPG (``fechaLiquidacion``) and AJUSTE
    (``credito_fechaLiquidacion`` / ``debito_fechaLiquidacion``) types.

    The expression is dialect-aware:
    - **PostgreSQL**: uses ``->>`` JSON text extraction.
    - **SQLite**: uses ``json_extract()`` for compatibility with the
      test database.

    Usage::

        expr = fecha_liquidacion_expr()
        query.filter(fecha_liquidacion_as_date(expr) >= some_date)
        query.order_by(fecha_liquidacion_as_date(expr).desc())
    """
    if _is_sqlite():
        return text(
            "COALESCE("
            "json_extract(datos_limpios, '$.fechaLiquidacion'), "
            "json_extract(datos_limpios, '$.credito_fechaLiquidacion'), "
            "json_extract(datos_limpios, '$.debito_fechaLiquidacion')"
            ")"
        )
    return text(
        "COALESCE("
        "datos_limpios->>'fechaLiquidacion', "
        "datos_limpios->>'credito_fechaLiquidacion', "
        "datos_limpios->>'debito_fechaLiquidacion'"
        ")"
    )


def fecha_liquidacion_as_date(expr: TextClause) -> ColumnElement:
    """Wrap *expr* so it can be compared against Python ``date`` objects.

    - **PostgreSQL**: ``CAST(expr AS DATE)`` — proper date type.
    - **SQLite**: ``date(expr)`` — SQLite ``date()`` returns an ISO-8601
      text value that compares correctly with date strings produced by
      SQLAlchemy parameter binding.

    Returns a :class:`ColumnElement` so that SQLAlchemy comparison
    operators (``>=``, ``<=``, ``.asc()``, etc.) work correctly.
    """
    if _is_sqlite():
        # SQLite date() returns 'YYYY-MM-DD' text — comparable as string.
        # literal_column() wraps raw SQL as a ColumnElement with full
        # operator support (>=, <=, .asc(), .desc()).
        return literal_column(f"date({expr.text})")
    return cast(expr, Date)
