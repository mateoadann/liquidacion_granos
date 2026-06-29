from __future__ import annotations

import io
import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request, send_file

from sqlalchemy import and_, cast, extract, Integer, or_, String

from ..extensions import db
from ..models import AuditEvent, CoeEstado, LpgDocument, Taxpayer, User
from ..middleware import require_auth, require_admin, get_current_user
from ..time_utils import now_cordoba_naive
from ..services import (
    PdfFetchError,
    PdfNoCertificatesError,
    PdfNotFoundError,
    extract_fecha_liquidacion,
    fecha_liquidacion_as_date,
    fecha_liquidacion_expr,
    get_or_fetch_pdf,
)
from ..services.lpg_document_utils import _is_sqlite, coe_already_exists
from ..services.lpg_manual_pipeline import (
    ArcaWsError,
    CoeAlreadyExistsError,
    InvalidCoeFormatError,
    LpgManualWsService,
    TaxpayerConfigInvalidError,
)

logger = logging.getLogger(__name__)

coes_bp = Blueprint("coes", __name__)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


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
        "controlada": bool(doc.controlada),
        "controlada_por": doc.controlada_por,
        "controlada_por_nombre": doc.controlada_por_nombre,
        "controlada_en": doc.controlada_en.isoformat() if doc.controlada_en else None,
        "cod_tipo_operacion": (doc.datos_limpios or {}).get("codTipoOperacion"),
    }
    if include_taxpayer and doc.taxpayer_id:
        taxpayer = db.session.get(Taxpayer, doc.taxpayer_id)
        if taxpayer:
            result["taxpayer"] = {
                "id": taxpayer.id,
                "empresa": taxpayer.empresa,
                "cuit": taxpayer.cuit,
                "cuit_representado": taxpayer.cuit_representado,
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
    fecha_desde = _parse_iso_date(request.args.get("fecha_desde", type=str))
    fecha_hasta = _parse_iso_date(request.args.get("fecha_hasta", type=str))
    search = request.args.get("search", type=str)

    query = db.session.query(LpgDocument)

    # Always exclude documents belonging to inactive taxpayers.
    query = query.join(Taxpayer, Taxpayer.id == LpgDocument.taxpayer_id).filter(
        Taxpayer.activo.is_(True)
    )

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

    tipo_cte_raw = request.args.get("tipo_cte", type=str)
    if tipo_cte_raw:
        tipos = {t.strip().upper() for t in tipo_cte_raw.split(",") if t.strip()}
        # Classification mirrors json_v7_exporter._build_comprobante — mutually exclusive
        # and based on tipo_documento + codTipoOperacion, NOT the COE prefix.
        # cast to String on a JSON path yields "2" when the stored value is the
        # JSON integer 2, but '"2"' (with surrounding quotes) when it is the JSON
        # string "2". Both representations mean F2, so we match either form.
        cod_col = cast(LpgDocument.datos_limpios["codTipoOperacion"], String)
        is_ajuste = LpgDocument.tipo_documento == "AJUSTE"
        # Covers JSON int 2 → "2"  AND  JSON string "2" → '"2"'
        is_cod2 = or_(cod_col == "2", cod_col == '"2"')
        clauses = []
        if "NL" in tipos:
            clauses.append(is_ajuste)
        if "F2" in tipos:
            clauses.append(and_(~is_ajuste, is_cod2))
        if "F1" in tipos:
            clauses.append(and_(~is_ajuste, or_(cod_col.is_(None), ~is_cod2)))
        if clauses:
            query = query.filter(or_(*clauses))

    controlada_raw = (request.args.get("controlada") or "").strip().lower()
    if controlada_raw == "true":
        query = query.filter(LpgDocument.controlada.is_(True))
    elif controlada_raw == "false":
        query = query.filter(LpgDocument.controlada.is_(False))

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


@coes_bp.patch("/coes/<int:coe_id>/controlada")
@require_auth
def toggle_coe_controlada(coe_id: int):
    """Toggle the controlada flag on a COE document."""
    body = request.get_json(silent=True) or {}
    new_value = body.get("controlada")
    if not isinstance(new_value, bool):
        return {"error": "controlada (boolean) requerido"}, 400

    doc = db.session.get(LpgDocument, coe_id)
    if not doc:
        return {"error": "COE no encontrado"}, 404

    prev_value = bool(doc.controlada)
    if prev_value == new_value:
        # No-op — return current state without emitting an audit event
        return _serialize_coe(doc, include_taxpayer=True), 200

    current_user = get_current_user() or {}
    username = current_user.get("username")

    # Resolve nombre from User table (one read per toggle; not on hot path)
    nombre: str | None = None
    if username:
        user_row = db.session.query(User).filter(User.username == username).first()
        nombre = user_row.nombre if user_row else None

    if new_value:
        doc.controlada = True
        doc.controlada_por = username
        doc.controlada_por_nombre = nombre
        doc.controlada_en = now_cordoba_naive()
    else:
        doc.controlada = False
        doc.controlada_por = None
        doc.controlada_por_nombre = None
        doc.controlada_en = None

    audit = AuditEvent(
        taxpayer_id=doc.taxpayer_id,
        operation="coe_controlada_toggle",
        level="info",
        metadata_json={
            "coe_id": doc.id,
            "coe": doc.coe,
            "from": prev_value,
            "to": new_value,
            "by_username": username,
            "by_nombre": nombre,
        },
    )
    db.session.add(audit)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("COE_CONTROLADA_TOGGLE_ERROR | coe_id=%s", coe_id)
        return {"error": "Error interno al actualizar controlada"}, 500

    return _serialize_coe(doc, include_taxpayer=True), 200


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


# ---------------------------------------------------------------------------
# Manual WS load endpoints
# ---------------------------------------------------------------------------


@coes_bp.post("/coes/consultar")
@require_auth
def consultar_coe():
    """POST /api/coes/consultar — read-only WS fetch. No DB writes."""
    body = request.get_json(silent=True) or {}
    coe = (body.get("coe") or "").strip()
    taxpayer_id = body.get("taxpayer_id")

    if not isinstance(taxpayer_id, int):
        return {"error": "taxpayer_id requerido"}, 400

    taxpayer = Taxpayer.query.filter_by(id=taxpayer_id, activo=True).first()
    if not taxpayer:
        return {"error": "Cliente no encontrado"}, 404

    try:
        result = LpgManualWsService().fetch_only(taxpayer, coe)
    except InvalidCoeFormatError as exc:
        return {"error": str(exc)}, 400
    except TaxpayerConfigInvalidError as exc:
        return {"error": str(exc)}, 422
    except ArcaWsError as exc:
        return {"error": str(exc)}, 422
    except Exception:
        logger.exception("CONSULTAR_COE_UNEXPECTED | taxpayer_id=%s coe=%s", taxpayer_id, coe)
        return {"error": "Error interno"}, 500

    existing = coe_already_exists(taxpayer_id, coe)
    return {
        "preview": result["preview"],
        "tipo_documento": result["tipo_documento"],
        "duplicado": existing is not None,
        "coe_id": existing.id if existing else None,
    }, 200


@coes_bp.post("/coes/consultar/pdf")
@require_auth
def consultar_coe_pdf():
    """POST /api/coes/consultar/pdf — fetch PDF for a COE without persisting.

    Calls ARCA WS with pdf="S" and streams the binary back. No DB writes,
    no PdfCache entry, no AuditEvent. Used by the manual-load modal to let
    the user preview/download the PDF before deciding to persist.
    """
    body = request.get_json(silent=True) or {}
    coe = (body.get("coe") or "").strip()
    taxpayer_id = body.get("taxpayer_id")

    if not isinstance(taxpayer_id, int):
        return {"error": "taxpayer_id requerido"}, 400

    taxpayer = Taxpayer.query.filter_by(id=taxpayer_id, activo=True).first()
    if not taxpayer:
        return {"error": "Cliente no encontrado"}, 404

    if not taxpayer.cert_crt_path or not taxpayer.cert_key_path:
        return {"error": "Cliente no tiene certificados ARCA configurados"}, 422

    from ..services.lpg_manual_pipeline import COE_PATTERN

    if not COE_PATTERN.match(coe):
        return {"error": "COE inválido. Debe ser numérico y tener entre 6 y 16 dígitos."}, 400

    import base64
    from pathlib import Path
    from ..integrations.arca.client import ArcaWslpgClient, ArcaDiscoveryConfig

    try:
        config = ArcaDiscoveryConfig.from_env()
        config.environment = taxpayer.ambiente or config.environment
        config.cuit_representada = taxpayer.cuit_representado
        config.cert_path = taxpayer.cert_crt_path
        config.key_path = taxpayer.cert_key_path
        ta_base = config.ta_path or "/tmp/ta"
        config.ta_path = str(Path(ta_base) / f"taxpayer_{taxpayer.id}")

        ws_client = ArcaWslpgClient(config=config)
        ws_client.connect()

        coe_int = int(coe)
        # Try LPG first; if WS returns the ajuste marker, retry as ajuste
        result = ws_client.call_liquidacion_x_coe(coe_int, pdf="S")
        data = (result or {}).get("data") or {}
        if isinstance(data, dict) and data.get("ajusteUnificado") is not None:
            result = ws_client.call_ajuste_x_coe(coe_int, pdf="S")
            data = (result or {}).get("data") or {}

        from ..services.lpg_manual_pipeline import _extract_arca_error

        arca_error = _extract_arca_error(result)
        if arca_error:
            return {"error": arca_error[1]}, 422

        pdf_raw = data.get("pdf") if isinstance(data, dict) else None
        if not pdf_raw:
            return {"error": "ARCA no devolvió PDF para este COE"}, 502

        if isinstance(pdf_raw, bytes):
            pdf_bytes = pdf_raw
        else:
            pdf_bytes = base64.b64decode(pdf_raw)
    except Exception:
        logger.exception(
            "CONSULTAR_COE_PDF_UNEXPECTED | taxpayer_id=%s coe=%s",
            taxpayer_id,
            coe,
        )
        return {"error": "Error al consultar PDF"}, 502

    filename = f"liquidacion_{coe}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@coes_bp.get("/coes/anios-disponibles")
@require_auth
def anios_disponibles():
    """Return the distinct years that have COEs, ordered descending.

    Derives the year from the same ``fecha_liquidacion_expr()`` used by the
    list endpoint so the values are always consistent.  Only documents
    belonging to active taxpayers are considered.
    """
    from sqlalchemy import func as sa_func, select

    fecha_liq_expr = fecha_liquidacion_expr()
    fecha_liq_date = fecha_liquidacion_as_date(fecha_liq_expr)

    if _is_sqlite():
        # SQLite: strftime('%Y', <iso-date-string>) → '2025' → cast to int.
        year_expr = cast(sa_func.strftime("%Y", fecha_liq_expr), Integer)
    else:
        # PostgreSQL: EXTRACT(year FROM CAST(expr AS DATE)) → numeric → cast to int.
        year_expr = cast(extract("year", fecha_liq_date), Integer)

    lpg_t = LpgDocument.__table__
    taxpayer_t = Taxpayer.__table__

    stmt = (
        select(year_expr.label("anio"))
        .select_from(lpg_t.join(taxpayer_t, taxpayer_t.c.id == lpg_t.c.taxpayer_id))
        .where(taxpayer_t.c.activo.is_(True))
        .where(fecha_liq_date.isnot(None))
        .distinct()
        .order_by(year_expr.desc())
    )

    rows = db.session.execute(stmt).all()
    anios = [row.anio for row in rows if row.anio is not None]
    return {"anios": anios}


@coes_bp.post("/coes/manual")
@require_auth
def cargar_coe_manual():
    """POST /api/coes/manual — persist COE from WS. Writes LpgDocument + AuditEvent."""
    body = request.get_json(silent=True) or {}
    coe = (body.get("coe") or "").strip()
    taxpayer_id = body.get("taxpayer_id")

    if not isinstance(taxpayer_id, int):
        return {"error": "taxpayer_id requerido"}, 400

    taxpayer = Taxpayer.query.filter_by(id=taxpayer_id, activo=True).first()
    if not taxpayer:
        return {"error": "Cliente no encontrado"}, 404

    try:
        doc = LpgManualWsService().fetch_and_persist(taxpayer, coe)
    except InvalidCoeFormatError as exc:
        return {"error": str(exc)}, 400
    except TaxpayerConfigInvalidError as exc:
        return {"error": str(exc)}, 422
    except CoeAlreadyExistsError as exc:
        return {"error": str(exc), "coe_id": exc.coe_id}, 409
    except ArcaWsError as exc:
        return {"error": str(exc)}, 422
    except Exception:
        logger.exception("CARGAR_COE_MANUAL_UNEXPECTED | taxpayer_id=%s coe=%s", taxpayer_id, coe)
        return {"error": "Error interno"}, 500

    return _serialize_coe(doc, include_taxpayer=True), 201
