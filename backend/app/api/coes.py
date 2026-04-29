from __future__ import annotations

import io
import logging

from flask import Blueprint, jsonify, request, send_file

from ..extensions import db
from ..models import CoeEstado, LpgDocument, Taxpayer
from ..middleware import require_auth, require_admin
from ..services import (
    PdfFetchError,
    PdfNoCertificatesError,
    PdfNotFoundError,
    extract_fecha_liquidacion,
    fecha_liquidacion_as_date,
    fecha_liquidacion_expr,
    get_or_fetch_pdf,
)

logger = logging.getLogger(__name__)

coes_bp = Blueprint("coes", __name__)


def _serialize_coe(doc: LpgDocument, include_taxpayer: bool = False) -> dict:
    # Include lifecycle estado from CoeEstado if exists
    coe_estado_info = None
    if doc.coe_estado:
        ce = doc.coe_estado
        coe_estado_info = {
            "estado": ce.estado,
            "descargado_en": ce.descargado_en.isoformat() if ce.descargado_en else None,
            "cargado_en": ce.cargado_en.isoformat() if ce.cargado_en else None,
            "error_fase": ce.error_fase,
            "error_mensaje": ce.error_mensaje,
        }

    result = {
        "id": doc.id,
        "taxpayer_id": doc.taxpayer_id,
        "coe": doc.coe,
        "pto_emision": doc.pto_emision,
        "nro_orden": doc.nro_orden,
        "estado": doc.estado,
        "tipo_documento": doc.tipo_documento,
        "fecha_liquidacion": extract_fecha_liquidacion(doc),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "raw_data": doc.raw_data,
        "datos_limpios": doc.datos_limpios,
        "coe_estado": coe_estado_info,
    }
    if include_taxpayer and doc.taxpayer_id:
        taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
        if taxpayer:
            result["taxpayer"] = {
                "id": taxpayer.id,
                "empresa": taxpayer.empresa,
                "cuit": taxpayer.cuit,
            }
    return result


@coes_bp.get("/coes")
@require_auth
def list_coes():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)  # Limitar a 100 max

    taxpayer_id = request.args.get("taxpayer_id", type=int)
    estado = request.args.get("estado", type=str)
    estado_ciclo = request.args.get("estado_ciclo", type=str)
    fecha_desde = request.args.get("fecha_desde", type=str)
    fecha_hasta = request.args.get("fecha_hasta", type=str)
    search = request.args.get("search", type=str)

    query = db.session.query(LpgDocument)

    if taxpayer_id:
        query = query.filter(LpgDocument.taxpayer_id == taxpayer_id)

    if estado:
        query = query.filter(LpgDocument.estado == estado)

    if estado_ciclo:
        query = query.outerjoin(
            CoeEstado, CoeEstado.lpg_document_id == LpgDocument.id
        ).filter(CoeEstado.estado == estado_ciclo)

    fecha_liq_expr = fecha_liquidacion_expr()
    fecha_liq_date = fecha_liquidacion_as_date(fecha_liq_expr)

    if fecha_desde:
        query = query.filter(fecha_liq_date >= fecha_desde)

    if fecha_hasta:
        query = query.filter(fecha_liq_date <= fecha_hasta)

    if search:
        query = query.filter(LpgDocument.coe.ilike(f"%{search}%"))

    total = query.count()
    pages = (total + per_page - 1) // per_page

    coes = (
        query.order_by(fecha_liq_date.desc(), LpgDocument.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "coes": [_serialize_coe(c) for c in coes],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@coes_bp.get("/coes/<int:coe_id>")
@require_auth
def get_coe(coe_id: int):
    doc = db.session.get(LpgDocument, coe_id)
    if not doc:
        return {"error": "COE no encontrado"}, 404
    return _serialize_coe(doc, include_taxpayer=True)


@coes_bp.get("/coes/<int:doc_id>/pdf")
@require_auth
def download_coe_pdf(doc_id):
    """Download the PDF for a given LpgDocument."""
    try:
        pdf_bytes, filename = get_or_fetch_pdf(doc_id)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except PdfNotFoundError:
        return {"error": "COE no encontrado"}, 404
    except PdfNoCertificatesError as exc:
        return {"error": str(exc)}, 503
    except PdfFetchError as exc:
        return {"error": str(exc)}, 502
    except Exception:
        logger.exception("PDF_DOWNLOAD_ERROR | doc_id=%s", doc_id)
        return {"error": "Error interno al descargar PDF"}, 500


@coes_bp.post("/coes/refetch-ajustes")
@require_auth
@require_admin
def refetch_ajustes():
    """Re-consulta COEs con error 1861 usando ajusteXCoeConsultar."""
    from ..integrations.arca.client import ArcaWslpgClient, ArcaDiscoveryConfig
    from ..services.datos_limpios_builder import DatosLimpiosBuilder
    import os
    from pathlib import Path

    docs = LpgDocument.query.filter(
        (LpgDocument.estado == None) | (LpgDocument.estado == "")  # noqa: E711
    ).all()

    if not docs:
        return jsonify({"message": "No hay COEs pendientes de re-consulta", "total": 0})

    results = []
    builder = DatosLimpiosBuilder()

    for doc in docs:
        if not doc.coe:
            continue
        taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
        if not taxpayer or not taxpayer.cert_crt_path or not taxpayer.cert_key_path:
            results.append({"id": doc.id, "coe": doc.coe, "ok": False, "error": "Sin certificados"})
            continue

        try:
            config = ArcaDiscoveryConfig.from_env()
            config.environment = taxpayer.ambiente or config.environment
            config.cuit_representada = taxpayer.cuit_representado
            config.cert_path = taxpayer.cert_crt_path
            config.key_path = taxpayer.cert_key_path
            ta_base = config.ta_path or os.getenv("ARCA_TA_PATH") or "/tmp/ta"
            config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")

            ws_client = ArcaWslpgClient(config=config)
            ws_result = ws_client.call_ajuste_x_coe(int(doc.coe), pdf="N")

            data = ws_result.get("data", {}) if isinstance(ws_result, dict) else {}
            ajuste = data.get("ajusteUnificado", {}) if isinstance(data, dict) else {}

            doc.raw_data = ws_result
            doc.tipo_documento = "AJUSTE"
            doc.estado = ajuste.get("estado") if isinstance(ajuste, dict) else None
            doc.pto_emision = ajuste.get("ptoEmision") if isinstance(ajuste, dict) else None
            doc.nro_orden = ajuste.get("nroOrden") if isinstance(ajuste, dict) else None
            db.session.commit()

            builder.process_document(doc)
            results.append({"id": doc.id, "coe": doc.coe, "ok": True, "estado": doc.estado})
            logger.info("REFETCH_AJUSTE_OK | doc_id=%s coe=%s estado=%s", doc.id, doc.coe, doc.estado)
        except Exception as exc:
            db.session.rollback()
            results.append({"id": doc.id, "coe": doc.coe, "ok": False, "error": str(exc)})
            logger.exception("REFETCH_AJUSTE_ERROR | doc_id=%s coe=%s", doc.id, doc.coe)

    return jsonify({
        "total": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "errors": sum(1 for r in results if not r["ok"]),
        "results": results,
    })
