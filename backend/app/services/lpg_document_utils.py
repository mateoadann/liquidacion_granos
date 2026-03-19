"""Shared helpers for extracting data from LpgDocument instances.

Centralises logic that was previously duplicated across API modules
(clients.py, coes.py) so that changes only need to happen in one place.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.sql.expression import TextClause

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


def fecha_liquidacion_expr() -> TextClause:
    """Return a SQL COALESCE expression over datos_limpios JSON fields.

    Covers both LPG (``fechaLiquidacion``) and AJUSTE
    (``credito_fechaLiquidacion`` / ``debito_fechaLiquidacion``) types.

    Usage::

        expr = fecha_liquidacion_expr()
        query.filter(cast(expr, Date) >= some_date)
        query.order_by(cast(expr, Date).desc())
    """
    return text(
        "COALESCE("
        "datos_limpios->>'fechaLiquidacion', "
        "datos_limpios->>'credito_fechaLiquidacion', "
        "datos_limpios->>'debito_fechaLiquidacion'"
        ")"
    )
