"""Shared helpers for LpgDocument extraction, persistence, and WS client construction.

Centralises logic used by both LpgPlaywrightPipelineService (batch) and
LpgManualWsService (manual), so that changes only need to happen in one place.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import cast, Date, literal_column, text
from sqlalchemy.sql.expression import ClauseElement, ColumnElement, TextClause

from ..extensions import db
from ..integrations.arca import ArcaWslpgClient
from ..integrations.arca.client import ArcaDiscoveryConfig
from ..models import LpgDocument
from ..models.taxpayer import Taxpayer
from .certificate_validator import (
    CertificateValidationError,
    validate_certificate_and_key_paths,
)
from .coe_estado_service import crear_pendiente
from .datos_limpios_builder import DatosLimpiosBuilder

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# WS client + pipeline helpers (shared between batch and manual pipelines)
# ---------------------------------------------------------------------------


def build_ws_client_for_taxpayer(taxpayer: Taxpayer) -> ArcaWslpgClient:
    """Build an ArcaWslpgClient configured for the given taxpayer.

    Scopes the TA token cache directory to the taxpayer's id so concurrent
    runs across taxpayers do not trample each other's token files.
    """
    config = ArcaDiscoveryConfig.from_env()
    config.environment = taxpayer.ambiente or config.environment
    config.cuit_representada = taxpayer.cuit_representado
    config.cert_path = taxpayer.cert_crt_path
    config.key_path = taxpayer.cert_key_path

    ta_base = config.ta_path or os.getenv("ARCA_TA_PATH") or "/tmp/ta"
    config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")
    return ArcaWslpgClient(config=config)


def validate_taxpayer_ws_config(taxpayer: Taxpayer) -> None:
    """Validate that *taxpayer* has all required fields for a WS call.

    Raises:
        ValueError: with a human-readable message indicating the missing field
            or invalid certificate.
    """
    if not taxpayer.cuit_representado:
        raise ValueError(f"Cliente id={taxpayer.id} sin cuit_representado.")
    if not taxpayer.cert_crt_path or not taxpayer.cert_key_path:
        raise ValueError(f"Cliente id={taxpayer.id} sin certificados cargados.")
    try:
        validate_certificate_and_key_paths(taxpayer.cert_crt_path, taxpayer.cert_key_path)
    except CertificateValidationError as exc:
        raise ValueError(
            f"Certificados inválidos para cliente id={taxpayer.id}: {exc}"
        ) from exc


def coe_already_exists(taxpayer_id: int, coe: str) -> LpgDocument | None:
    """Return the existing LpgDocument for *(taxpayer_id, coe)*, or None.

    Scoped to the taxpayer so two clients can have the same COE string
    without interfering with each other's deduplication.
    """
    return LpgDocument.query.filter_by(taxpayer_id=taxpayer_id, coe=coe).first()


def _find_key(value: Any, keys: set[str]) -> Any:
    """Depth-first search for the first matching key in a nested dict/list."""
    lowered = {item.casefold() for item in keys}
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if str(key).casefold() in lowered:
                    return child
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _to_int(value: Any) -> int | None:
    """Extract an integer from *value*, stripping non-digit characters."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _to_str(value: Any) -> str | None:
    """Coerce *value* to a stripped string, returning None for blank values."""
    if value is None:
        return None
    text_val = str(value).strip()
    return text_val or None


def save_lpg_document_from_ws(
    taxpayer_id: int,
    coe: str,
    ws_result: dict[str, Any],
    tipo_documento: str = "LPG",
) -> LpgDocument:
    """Persist an LpgDocument from a raw WS payload, then run post-save hooks.

    Commits the document immediately so that downstream callers (DatosLimpiosBuilder,
    crear_pendiente) can reference the assigned ``id``.  Mirrors the behaviour
    originally implemented in ``LpgPlaywrightPipelineService._save_lpg_document``.

    Args:
        taxpayer_id: FK to the owning Taxpayer.
        coe: The COE string identifier.
        ws_result: Raw parsed dict returned by ArcaWslpgClient.
        tipo_documento: ``"LPG"`` (default) or ``"AJUSTE"``.

    Returns:
        The committed LpgDocument instance.
    """
    data = ws_result.get("data") if isinstance(ws_result, dict) else ws_result
    document = LpgDocument()
    document.taxpayer_id = taxpayer_id
    document.coe = coe
    document.tipo_documento = tipo_documento
    document.pto_emision = _to_int(_find_key(data, {"ptoEmision", "pto_emision"}))
    document.nro_orden = _to_int(_find_key(data, {"nroOrden", "nro_orden"}))
    document.estado = _to_str(_find_key(data, {"estado", "estadoLiquidacion"}))
    document.raw_data = ws_result
    db.session.add(document)
    db.session.commit()

    builder = DatosLimpiosBuilder()
    builder.process_document(document)

    # Auto-create CoeEstado tracking entry (best-effort)
    if document.coe:
        try:
            crear_pendiente(document)
        except Exception:
            logger.exception(
                "SAVE_LPG_DOCUMENT_CREAR_PENDIENTE_ERROR | coe=%s taxpayer_id=%s",
                coe,
                taxpayer_id,
            )

    return document
