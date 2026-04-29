from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..middleware import require_api_key, require_admin_token
from ..services.coe_estado_service import (
    reportar_cargado,
    consultar_estado,
    listar_estados,
    forzar_sincronizado,
    TransicionInvalidaError,
    HashMismatchError,
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
