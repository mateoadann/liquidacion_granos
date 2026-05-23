"""LpgManualWsService — two-step manual COE load flow.

Exposes:
  * fetch_only     — pure WS read; NO db writes, NO audit.
  * fetch_and_persist — calls fetch_only, then dedupes + persists + audits.

Typed exceptions map 1-to-1 to HTTP codes in the API layer:
  InvalidCoeFormatError  → 400
  TaxpayerConfigInvalidError → 422
  CoeAlreadyExistsError  → 409  (fetch_and_persist only)
  ArcaWsError            → 502
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..extensions import db
from ..models import AuditEvent, LpgDocument, Taxpayer
from .lpg_document_utils import (
    build_ws_client_for_taxpayer,
    coe_already_exists,
    save_lpg_document_from_ws,
    validate_taxpayer_ws_config,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed exception hierarchy
# ---------------------------------------------------------------------------

COE_PATTERN = re.compile(r"^\d{6,16}$")


class LpgManualError(Exception):
    """Base for service errors mappable to HTTP codes."""


class InvalidCoeFormatError(LpgManualError):
    """400 — coe string failed regex / type check."""


class TaxpayerConfigInvalidError(LpgManualError):
    """422 — taxpayer missing/invalid certs or cuit_representado."""


class CoeAlreadyExistsError(LpgManualError):
    """409 — used only in fetch_and_persist. Holds existing coe_id."""

    def __init__(self, coe_id: int, message: str = "Esta liquidación ya está cargada") -> None:
        super().__init__(message)
        self.coe_id = coe_id


class ArcaWsError(LpgManualError):
    """502 — ARCA upstream failure (auth, timeout, functional, parser)."""


# ---------------------------------------------------------------------------
# Pure helper: build preview dict from WS result (no DB access)
# ---------------------------------------------------------------------------


def build_preview_from_ws(ws_result: dict[str, Any], tipo_documento: str) -> dict[str, Any]:
    """Build a serialisation-compatible preview dict from a raw WS result.

    Shape mirrors the DB-persisted form used by ``_serialize_coe``, but without
    the id / created_at / coe_estado fields (which don't exist before persist).
    """
    data = ws_result.get("data") if isinstance(ws_result, dict) else ws_result
    if not isinstance(data, dict):
        data = {}

    def _find(keys: set[str]) -> Any:
        """Depth-first search for the first matching key."""
        stack = [data]
        lowered = {k.casefold() for k in keys}
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

    def _to_int_safe(v: Any) -> int | None:
        if v is None:
            return None
        digits = re.sub(r"\D", "", str(v))
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    return {
        "tipo_documento": tipo_documento,
        "pto_emision": _to_int_safe(_find({"ptoEmision", "pto_emision"})),
        "nro_orden": _to_int_safe(_find({"nroOrden", "nro_orden"})),
        "estado": str(_find({"estado", "estadoLiquidacion"}) or "").strip() or None,
        "raw_data": ws_result,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LpgManualWsService:
    """Domain service for the two-step consultar → cargar flow."""

    # ------------------------------------------------------------------ #
    # fetch_only — pure read, NO side effects                             #
    # ------------------------------------------------------------------ #

    def fetch_only(self, taxpayer: Taxpayer, coe: str) -> dict[str, Any]:
        """Validate, call ARCA WS, return parsed dict. NO db.session writes.

        Returns:
            {
                "ws_result": dict,      # raw parsed WS payload
                "tipo_documento": str,  # "LPG" | "AJUSTE"
                "preview": dict,        # shape compatible with _serialize_coe (db-free)
            }

        Raises:
            InvalidCoeFormatError
            TaxpayerConfigInvalidError
            ArcaWsError
        """
        # 1. Validate COE format
        coe_stripped = coe.strip() if coe else ""
        if not COE_PATTERN.match(coe_stripped):
            raise InvalidCoeFormatError(
                f"COE inválido: '{coe}'. Debe ser numérico y tener entre 6 y 16 dígitos."
            )

        # 2. Validate taxpayer WS config
        try:
            validate_taxpayer_ws_config(taxpayer)
        except ValueError as exc:
            raise TaxpayerConfigInvalidError(str(exc)) from exc

        # 3. Build WS client
        ws_client = build_ws_client_for_taxpayer(taxpayer)
        coe_int = int(coe_stripped)

        # 4. Call WS — with ajuste fallback
        tipo_documento = "LPG"
        try:
            logger.info(
                "MANUAL_WS_FETCH | taxpayer_id=%s coe=%s", taxpayer.id, coe_stripped
            )
            ws_result = ws_client.call_liquidacion_x_coe(coe_int, pdf="N")
        except Exception as primary_exc:
            logger.warning(
                "MANUAL_WS_FETCH_FALLBACK | taxpayer_id=%s coe=%s primary_error=%s",
                taxpayer.id,
                coe_stripped,
                primary_exc,
            )
            try:
                ws_result = ws_client.call_ajuste_x_coe(coe_int, pdf="N")
                tipo_documento = "AJUSTE"
            except Exception as fallback_exc:
                logger.error(
                    "MANUAL_WS_FETCH_ERROR | taxpayer_id=%s coe=%s fallback_error=%s",
                    taxpayer.id,
                    coe_stripped,
                    fallback_exc,
                )
                raise ArcaWsError(
                    f"Error al consultar ARCA: {fallback_exc}"
                ) from fallback_exc

        preview = build_preview_from_ws(ws_result, tipo_documento)
        return {
            "ws_result": ws_result,
            "tipo_documento": tipo_documento,
            "preview": preview,
        }

    # ------------------------------------------------------------------ #
    # fetch_and_persist — command path, commits                           #
    # ------------------------------------------------------------------ #

    def fetch_and_persist(self, taxpayer: Taxpayer, coe: str) -> LpgDocument:
        """Fetch WS, dedupe, persist LpgDocument, write AuditEvent, return doc.

        Raises:
            InvalidCoeFormatError
            TaxpayerConfigInvalidError
            CoeAlreadyExistsError  — if coe already stored for this taxpayer
            ArcaWsError
        """
        coe_stripped = coe.strip() if coe else ""

        # 1. Fresh WS fetch (always re-fetches; never trusts client preview)
        result = self.fetch_only(taxpayer, coe_stripped)

        # 2. Dedupe check
        existing = coe_already_exists(taxpayer.id, coe_stripped)
        if existing is not None:
            raise CoeAlreadyExistsError(coe_id=existing.id)

        # 3. Persist
        doc = save_lpg_document_from_ws(
            taxpayer.id,
            coe_stripped,
            result["ws_result"],
            result["tipo_documento"],
        )

        # 4. Audit event (best-effort: failure does NOT roll back the persist)
        try:
            event = AuditEvent()
            event.operation = "coe_carga_manual"
            event.taxpayer_id = taxpayer.id
            event.metadata_json = {
                "coe": coe_stripped,
                "tipo_documento": result["tipo_documento"],
                "lpg_document_id": doc.id,
            }
            db.session.add(event)
            db.session.commit()
        except Exception:
            logger.exception(
                "MANUAL_AUDIT_EVENT_ERROR | taxpayer_id=%s coe=%s doc_id=%s",
                taxpayer.id,
                coe_stripped,
                doc.id,
            )

        return doc
