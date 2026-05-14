from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..middleware import require_api_key, require_admin_token
from ..models import LpgDocument, Taxpayer
from ..services.coe_estado_service import (
    reportar_cargado,
    consultar_estado,
    listar_estados,
    forzar_sincronizado,
    TransicionInvalidaError,
    HashMismatchError,
)
from ..services.lpg_document_utils import (
    fecha_liquidacion_as_date,
    fecha_liquidacion_expr,
)
from ..time_utils import now_cordoba_naive

integration_bp = Blueprint("integration", __name__)


@integration_bp.get("/v1/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": now_cordoba_naive().isoformat(),
        "version": "1.0.0",
    })


@integration_bp.post("/v1/coes/cargado")
@require_api_key
def post_coe_cargado():
    body = request.get_json(silent=True) or {}

    # Validate required fields
    coe = body.get("coe")
    if not coe:
        return jsonify({"error": "validacion_fallida", "mensaje": "Campo 'coe' requerido."}), 422

    estado = body.get("estado")
    if estado not in ("ok", "error"):
        return jsonify({"error": "validacion_fallida", "mensaje": "Campo 'estado' debe ser 'ok' o 'error'."}), 422

    required = ["ejecucion_id", "usuario", "cargado_en", "hash_payload"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": "validacion_fallida", "mensaje": f"Campos requeridos faltantes: {', '.join(missing)}"}), 422

    if estado == "ok" and not body.get("comprobante"):
        return jsonify({"error": "validacion_fallida", "mensaje": "'comprobante' requerido cuando estado='ok'."}), 422

    if estado == "error" and not body.get("error_fase"):
        return jsonify({"error": "validacion_fallida", "mensaje": "'error_fase' requerido cuando estado='error'."}), 422

    try:
        result = reportar_cargado(body)
        return jsonify(result), 200
    except TransicionInvalidaError as e:
        return jsonify({
            "error": "transicion_invalida",
            "mensaje": str(e),
            "detalle": {"estado_actual": e.estado_actual},
        }), 409
    except HashMismatchError as e:
        return jsonify({
            "error": "payload_mismatch",
            "mensaje": "El hash del payload difiere del emitido.",
            "detalle": {
                "hash_emitido": e.hash_emitido,
                "hash_recibido": e.hash_recibido,
            },
        }), 409
    except Exception as e:
        return jsonify({"error": "interno", "mensaje": str(e)}), 500


@integration_bp.get("/v1/coes/<coe>")
@require_api_key
def get_coe_estado(coe):
    result = consultar_estado(coe)
    if result is None:
        return jsonify({"error": "coe_no_encontrado", "mensaje": f"COE {coe} no existe en la base."}), 404
    return jsonify(result), 200


@integration_bp.get("/v1/coes/estados")
@require_api_key
def get_coes_estados():
    cuit_empresa = request.args.get("cuit_empresa")
    estado = request.args.get("estado")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if limit > 500:
        limit = 500

    result = listar_estados(
        cuit_empresa=cuit_empresa,
        estado=estado,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )
    return jsonify(result), 200


@integration_bp.post("/v1/coes/<coe>/forzar-sincronizado")
@require_api_key
@require_admin_token
def post_coe_forzar_sincronizado(coe):
    body = request.get_json(silent=True) or {}

    estado = body.get("estado")
    if estado not in ("cargado", "error"):
        return jsonify({
            "error": "validacion_fallida",
            "mensaje": "Campo 'estado' debe ser 'cargado' o 'error'.",
        }), 422

    razon = body.get("razon", "")
    if not razon or len(razon) < 3:
        return jsonify({
            "error": "validacion_fallida",
            "mensaje": "Campo 'razon' requerido (>= 3 chars).",
        }), 422

    required = ["usuario", "forzado_en", "hash_payload_local"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({
            "error": "validacion_fallida",
            "mensaje": f"Campos requeridos faltantes: {', '.join(missing)}",
        }), 422

    if estado == "cargado":
        if not body.get("comprobante"):
            return jsonify({
                "error": "validacion_fallida",
                "mensaje": "'comprobante' requerido cuando estado='cargado'.",
            }), 422
        if not body.get("ejecucion_id"):
            return jsonify({
                "error": "validacion_fallida",
                "mensaje": "'ejecucion_id' requerido cuando estado='cargado'.",
            }), 422
        if not body.get("cargado_en"):
            return jsonify({
                "error": "validacion_fallida",
                "mensaje": "'cargado_en' requerido cuando estado='cargado'.",
            }), 422
    else:  # error
        if not body.get("error_fase"):
            return jsonify({
                "error": "validacion_fallida",
                "mensaje": "'error_fase' requerido cuando estado='error'.",
            }), 422
        if not body.get("error_mensaje"):
            return jsonify({
                "error": "validacion_fallida",
                "mensaje": "'error_mensaje' requerido cuando estado='error'.",
            }), 422

    try:
        result = forzar_sincronizado(coe, body)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({
            "error": "coe_no_encontrado",
            "mensaje": str(e),
        }), 404
    except Exception as e:
        return jsonify({"error": "interno", "mensaje": str(e)}), 500


# -----------------------------------------------------------------------
# GET /v2/liquidaciones — universo bulk read-only (PR3 plan v2)
# -----------------------------------------------------------------------


def _parse_iso_date(value: str, field: str) -> datetime:
    """Parse YYYY-MM-DD or raise ValueError with the field name."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(field) from exc


@integration_bp.get("/v2/liquidaciones")
@require_api_key
def get_v2_liquidaciones():
    """Universo bulk de liquidaciones v7.1 para rpa-holistor.

    Read-only: no modifica estado de ningún COE. La transición a 'cargado'
    sigue siendo responsabilidad de POST /v1/coes/cargado.

    Query params:
        desde_fecha_emision (opcional, ISO YYYY-MM-DD): filtro inferior
            por datos_limpios.fechaLiquidacion.
        hasta_fecha_emision (opcional, ISO YYYY-MM-DD): filtro superior
            por datos_limpios.fechaLiquidacion.
        cuit_empresa (opcional, repetible): filtra por
            Taxpayer.cuit_representado IN (cuits).

    Siempre se filtra server-side por Taxpayer.activo == True y
    Taxpayer.scheduler_activo == True. NO se filtra por CoeEstado.estado:
    el SPEC §18 indica que devolvemos el universo completo y rpa-holistor
    reconcilia contra su propio ledger.
    """
    desde_raw = request.args.get("desde_fecha_emision")
    hasta_raw = request.args.get("hasta_fecha_emision")
    cuits = request.args.getlist("cuit_empresa")

    desde_date = None
    hasta_date = None
    try:
        if desde_raw:
            desde_date = _parse_iso_date(desde_raw, "desde_fecha_emision").date()
        if hasta_raw:
            hasta_date = _parse_iso_date(hasta_raw, "hasta_fecha_emision").date()
    except ValueError as exc:
        campo = str(exc)
        return jsonify({
            "error": "validacion_fallida",
            "mensaje": "Fecha mal formada. Formato esperado: YYYY-MM-DD.",
            "detalle": {"campo": campo, "valor": request.args.get(campo)},
        }), 422

    query = (
        db.session.query(LpgDocument)
        .join(Taxpayer, LpgDocument.taxpayer_id == Taxpayer.id)
        .filter(Taxpayer.activo.is_(True))
        .filter(Taxpayer.scheduler_activo.is_(True))
    )

    if cuits:
        query = query.filter(Taxpayer.cuit_representado.in_(cuits))

    if desde_date is not None or hasta_date is not None:
        fecha_col = fecha_liquidacion_as_date(fecha_liquidacion_expr())
        if desde_date is not None:
            query = query.filter(fecha_col >= desde_date)
        if hasta_date is not None:
            query = query.filter(fecha_col <= hasta_date)

    docs = query.all()

    from ..services.json_v7_exporter import build_json_v7_bulk

    filtros = {
        "desde_fecha_emision": desde_raw,
        "hasta_fecha_emision": hasta_raw,
        "cuit_empresa": cuits or None,
    }
    body = build_json_v7_bulk(docs, filtros)
    return jsonify(body), 200


@integration_bp.get("/v2/empresas")
@require_api_key
def get_v2_empresas():
    """Universo de empresas activas + config scheduler.

    Read-only. La usa rpa-holistor para:
    - Poblar selector múltiple en modal Cargar.
    - Detectar empresas con scheduler caído (ultimo_scrape_error != null).

    A diferencia de GET /v2/liquidaciones, este endpoint SÍ incluye
    taxpayers con scheduler_activo=False (rpa-holistor los muestra con
    un flag visual, pero los lista para que el operador los vea).
    """
    taxpayers = (
        Taxpayer.query
        .filter(Taxpayer.activo.is_(True))
        .filter(Taxpayer.cuit_representado != "")
        .order_by(Taxpayer.empresa)
        .all()
    )

    ultimo_global = db.session.query(
        db.func.max(Taxpayer.scheduler_ultimo_ok)
    ).scalar()

    return jsonify({
        "total": len(taxpayers),
        "ultimo_scrape_global": (
            ultimo_global.isoformat() if ultimo_global else None
        ),
        "empresas": [
            {
                "cuit_empresa": t.cuit_representado,
                "razon_social": t.empresa,
                "scheduler": {
                    "activo": t.scheduler_activo,
                    "dias_semana": [
                        d.strip()
                        for d in (t.scheduler_dias_semana or "").split(",")
                        if d.strip()
                    ],
                    "hora_local": t.scheduler_hora_local,
                    "ultimo_scrape_ok": (
                        t.scheduler_ultimo_ok.isoformat()
                        if t.scheduler_ultimo_ok else None
                    ),
                    "ultimo_scrape_error": t.scheduler_ultimo_error,
                },
            }
            for t in taxpayers
        ],
    }), 200
