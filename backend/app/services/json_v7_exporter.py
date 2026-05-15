from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


def _format_cuit(cuit_value: Any) -> str:
    """Convert int/str/hyphenated CUIT to 11-digit zero-padded string."""
    if cuit_value is None:
        return ""
    raw = re.sub(r"[^0-9]", "", str(cuit_value))
    return raw.zfill(11)


TIPO_PTO_VTA_POR_CODIGO = {
    "F1": 3301,
    "F2": 3302,
    # "NL": TBD — consultar
}


def _build_comprobante(doc: Any, datos: dict) -> dict:
    """Build comprobante object from document and datos_limpios."""
    # Determine codigo
    if getattr(doc, "tipo_documento", None) == "AJUSTE":
        codigo = "NL"
    elif str(datos.get("codTipoOperacion", "")) == "2":
        codigo = "F2"
    else:
        codigo = "F1"

    coe = getattr(doc, "coe", "") or ""

    # nro from doc fields or COE split
    nro_orden = getattr(doc, "nro_orden", None)
    nro = int(nro_orden) if nro_orden is not None else (
        int(coe[4:]) if len(coe) > 4 else 0
    )

    # tipo_pto_vta is FIXED per comprobante type, NOT from the LPG
    tipo_pto_vta = TIPO_PTO_VTA_POR_CODIGO.get(codigo, 0)

    return {
        "codigo": codigo,
        "tipo_pto_vta": tipo_pto_vta,
        "nro": nro,
        "fecha_emision": datos.get("fechaLiquidacion", ""),
    }


def _safe_round(value: Any, decimals: int = 2) -> float:
    """Round a numeric value safely, returning 0.0 for non-numeric input."""
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return 0.0


def _build_grano(datos: dict) -> dict:
    """Map grain data from datos_limpios to v7 format."""
    return {
        "cod_grano": datos.get("codGrano"),
        "precio_unitario": _safe_round(datos.get("precioOperacion")),
        "cantidad_kg": int(datos.get("totalPesoNeto", 0)),
        "neto_total": _safe_round(datos.get("subTotal")),
        "iva_monto": _safe_round(datos.get("importeIva")),
        "subtotal": _safe_round(datos.get("operacionConIva")),
    }


def _build_retenciones(datos: dict) -> list[dict]:
    """Map retenciones from datos_limpios to v7 format.

    Unifies IB (Ingresos Brutos) and OG (Otras Retenciones) into a single
    IB entry, summing importes and alicuotas.
    """
    raw_retenciones = datos.get("retenciones", [])
    if not isinstance(raw_retenciones, list):
        raw_retenciones = []

    cuit_proveedor = _format_cuit(datos.get("cuitComprador"))

    ib_items: list[dict] = []
    og_items: list[dict] = []
    others: list[dict] = []

    for ret in raw_retenciones:
        codigo = ret.get("codigoConcepto", "")
        importe = ret.get("importeRetencion", 0) or 0
        if importe <= 0:
            continue
        if codigo == "IB":
            ib_items.append(ret)
        elif codigo == "OG":
            og_items.append(ret)
        else:
            others.append(ret)

    result: list[dict] = []

    # Unify IB + OG into single IB entry
    if ib_items or og_items:
        combined = ib_items + og_items
        total_importe = sum((r.get("importeRetencion", 0) or 0) for r in combined)
        total_alicuota = sum((r.get("alicuota", 0) or 0) for r in combined)
        result.append({
            "codigo_arca": "IB",
            "importe": _safe_round(total_importe),
            "alicuota": _safe_round(total_alicuota),
            "cuit_proveedor": cuit_proveedor,
        })

    # Add remaining retenciones as-is
    for ret in others:
        result.append({
            "codigo_arca": ret.get("codigoConcepto", ""),
            "importe": _safe_round(ret.get("importeRetencion", 0)),
            "alicuota": _safe_round(ret.get("alicuota", 0)),
            "cuit_proveedor": cuit_proveedor,
        })

    return result


def _build_deducciones(datos: dict) -> list[dict]:
    """Map deducciones from datos_limpios to v7 format."""
    raw_deducciones = datos.get("deducciones", [])
    if not isinstance(raw_deducciones, list):
        raw_deducciones = []

    cuit_proveedor = _format_cuit(datos.get("cuitComprador"))

    result: list[dict] = []
    for ded in raw_deducciones:
        importe = ded.get("importeDeduccion", 0) or 0
        if importe <= 0:
            continue
        result.append({
            "codigo_arca": ded.get("codigoConcepto", ""),
            "detalle": ded.get("detalleAclaratorio") or ded.get("descConcepto", ""),
            "base": _safe_round(ded.get("baseCalculo", 0)),
            "importe": _safe_round(importe),
            "alicuota_iva": _safe_round(ded.get("alicuotaIva", 0)),
            "importe_iva": _safe_round(ded.get("importeIva", 0)),
            "cuit_proveedor": cuit_proveedor,
        })

    return result


def transform_single(
    doc: Any,
    taxpayer: Any,
    mes: int,
    anio: int,
    id_liquidacion: str | None = None,
    estado_origen: str | None = None,
) -> dict:
    """Build a single v7.1 liquidacion dict from an LpgDocument."""
    datos = getattr(doc, "datos_limpios", None) or {}

    cuit_empresa = _format_cuit(getattr(taxpayer, "cuit_representado", None))
    cuit_comprador = _format_cuit(datos.get("cuitComprador"))

    comprobante = _build_comprobante(doc, datos)
    grano = _build_grano(datos)
    retenciones = _build_retenciones(datos)
    deducciones = _build_deducciones(datos)

    coe = getattr(doc, "coe", None) or ""

    liquidacion: dict[str, Any] = {
        "coe": coe,
        "id_liquidacion": id_liquidacion or f"liq_{uuid.uuid4().hex[:12]}",
        "estado_origen": estado_origen or "pendiente",
        "cuit_empresa": cuit_empresa,
        "cuit_comprador": cuit_comprador,
        "mes": mes,
        "anio": anio,
        "comprobante": comprobante,
        "grano": grano,
    }

    if retenciones or deducciones:
        liquidacion["cuit_proveedor"] = _format_cuit(datos.get("cuitComprador"))
        liquidacion["retenciones"] = retenciones
        liquidacion["deducciones"] = deducciones

    return liquidacion


# DEPRECATED: retirar en próxima iteración. Solo build_json_v7_bulk es el camino v2.
def build_json_v7(documents: list, taxpayer: Any, mes: int, anio: int) -> dict:
    """Build the full v7.1 JSON export from a list of LpgDocuments.

    Includes schema_version, meta block, and per-liquidation coe/id/estado.
    Transitions CoeEstado from pendiente→descargado and persists hash.
    Filters out COEs with estado='cargado'.
    """
    from .coe_estado_service import calcular_hash, marcar_descargado
    from ..models.coe_estado import CoeEstado

    now = datetime.now().astimezone()
    batch_id = f"b_{now.strftime('%Y%m%d_%H%M%S')}"

    liquidaciones = []
    for doc in documents:
        coe = getattr(doc, "coe", None) or ""

        # Check CoeEstado — skip if already cargado
        coe_estado_entry = None
        if coe:
            coe_estado_entry = CoeEstado.query.filter_by(coe=coe).first()
            if coe_estado_entry and coe_estado_entry.estado == "cargado":
                logger.info("EXPORT_SKIP_CARGADO | coe=%s", coe)
                continue

        # Determine estado_origen and id_liquidacion from CoeEstado
        estado_origen = coe_estado_entry.estado if coe_estado_entry else "pendiente"
        id_liquidacion = (
            coe_estado_entry.id_liquidacion if coe_estado_entry else None
        ) or f"liq_{uuid.uuid4().hex[:12]}"

        liq = transform_single(
            doc, taxpayer, mes, anio,
            id_liquidacion=id_liquidacion,
            estado_origen=estado_origen,
        )

        # Calculate hash and transition to descargado
        if coe and coe_estado_entry:
            h = calcular_hash(liq)
            try:
                marcar_descargado(coe, h, id_liquidacion)
            except Exception:
                logger.exception("EXPORT_MARCAR_DESCARGADO_ERROR | coe=%s", coe)

        liquidaciones.append(liq)

    return {
        "schema_version": "v7.1",
        "meta": {
            "generado_en": now.isoformat(timespec="seconds"),
            "generador": "liquidador-granos@1.0.0",
            "batch_id": batch_id,
        },
        "liquidaciones": liquidaciones,
    }


def build_json_v7_bulk(docs: list, filtros: dict) -> dict:
    """Build a v7.1 JSON export from multiple taxpayers (read-only, no side-effects).

    Used by GET /v2/liquidaciones (PR3). Differences with build_json_v7():

    - NO side-effects: does NOT transition CoeEstado, does NOT compute/persist
      hash, does NOT call marcar_descargado(). Pure read-only construction.
    - NO filtering by estado='cargado': returns the full universe matching
      the SQL-level filtros provided by the caller. rpa-holistor reconciles
      against its own local ledger.
    - Expects docs already filtered by the caller (SQL JOIN/WHERE on
      taxpayer + temporal range). This function only assembles the JSON.
    - Reads taxpayer from each doc via doc.taxpayer relationship. If a doc
      has no taxpayer, it is skipped with a logger.warning (not fatal).
    - mes/anio are derived from datos_limpios.fechaLiquidacion (ISO
      YYYY-MM-DD). If missing or invalid, the doc is skipped with a warning.
    - estado_origen / id_liquidacion come from CoeEstado.query.filter_by(coe).
      If no CoeEstado row exists, default to estado_origen="pendiente" and
      id_liquidacion=None (transform_single generates a uuid one).
    - meta block is enriched with fuente="api_v2_liquidaciones",
      filtros_aplicados=filtros, and total_liquidaciones.
    - generador is "liquidacion-granos@2.0.0" to distinguish from v1.
    """
    from ..models.coe_estado import CoeEstado

    generado_en = now_cordoba_naive().isoformat(timespec="seconds")

    liquidaciones: list[dict] = []
    for doc in docs:
        taxpayer = getattr(doc, "taxpayer", None)
        if taxpayer is None:
            logger.warning(
                "BULK_EXPORT_SKIP_NO_TAXPAYER | doc_id=%s coe=%s",
                getattr(doc, "id", None),
                getattr(doc, "coe", None),
            )
            continue

        datos = getattr(doc, "datos_limpios", None) or {}
        fecha_liq = datos.get("fechaLiquidacion")
        try:
            parsed = datetime.strptime(str(fecha_liq), "%Y-%m-%d")
            mes = parsed.month
            anio = parsed.year
        except (TypeError, ValueError):
            logger.warning(
                "BULK_EXPORT_SKIP_INVALID_FECHA | doc_id=%s coe=%s fecha=%r",
                getattr(doc, "id", None),
                getattr(doc, "coe", None),
                fecha_liq,
            )
            continue

        coe = getattr(doc, "coe", None) or ""
        coe_estado_entry = None
        if coe:
            coe_estado_entry = CoeEstado.query.filter_by(coe=coe).first()

        estado_origen = (
            coe_estado_entry.estado if coe_estado_entry else "pendiente"
        )
        id_liquidacion = (
            coe_estado_entry.id_liquidacion if coe_estado_entry else None
        )

        liq = transform_single(
            doc,
            taxpayer,
            mes,
            anio,
            id_liquidacion=id_liquidacion,
            estado_origen=estado_origen,
        )
        liquidaciones.append(liq)

    return {
        "schema_version": "v7.1",
        "meta": {
            "generado_en": generado_en,
            "generador": "liquidacion-granos@2.0.0",
            "fuente": "api_v2_liquidaciones",
            "filtros_aplicados": filtros,
            "total_liquidaciones": len(liquidaciones),
        },
        "liquidaciones": liquidaciones,
    }
