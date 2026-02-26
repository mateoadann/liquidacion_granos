from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..integrations.arca import ArcaIntegrationError, ArcaWslpgClient

wslpg_mvp_bp = Blueprint("wslpg_mvp", __name__)


def _client() -> ArcaWslpgClient:
    return ArcaWslpgClient()


def _parse_int(value: str | int | None, field_name: str) -> int:
    if value is None or str(value).strip() == "":
        raise ArcaIntegrationError(f"'{field_name}' es obligatorio.")
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ArcaIntegrationError(f"'{field_name}' debe ser numérico.") from exc


@wslpg_mvp_bp.get("/wslpg/mvp/dummy")
def mvp_dummy():
    try:
        result = _client().call_dummy()
        return jsonify({"ok": True, "operation": "dummy", **result})
    except ArcaIntegrationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Error inesperado: {exc}"}), 500


@wslpg_mvp_bp.post("/wslpg/mvp/liquidacion-ultimo-nro-orden")
def mvp_liquidacion_ultimo_nro_orden():
    try:
        payload = request.get_json(silent=True) or {}
        pto_emision = _parse_int(payload.get("ptoEmision"), "ptoEmision")
        result = _client().call_liquidacion_ultimo_nro_orden(pto_emision)
        return jsonify(
            {
                "ok": True,
                "operation": "liquidacionUltimoNroOrdenConsultar",
                "request": {"ptoEmision": pto_emision},
                **result,
            }
        )
    except ArcaIntegrationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Error inesperado: {exc}"}), 500


@wslpg_mvp_bp.post("/wslpg/mvp/liquidacion-x-nro-orden")
def mvp_liquidacion_x_nro_orden():
    try:
        payload = request.get_json(silent=True) or {}
        pto_emision = _parse_int(payload.get("ptoEmision"), "ptoEmision")
        nro_orden = _parse_int(payload.get("nroOrden"), "nroOrden")
        result = _client().call_liquidacion_x_nro_orden(pto_emision, nro_orden)
        return jsonify(
            {
                "ok": True,
                "operation": "liquidacionXNroOrdenConsultar",
                "request": {"ptoEmision": pto_emision, "nroOrden": nro_orden},
                **result,
            }
        )
    except ArcaIntegrationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Error inesperado: {exc}"}), 500


@wslpg_mvp_bp.post("/wslpg/mvp/liquidacion-x-coe")
def mvp_liquidacion_x_coe():
    try:
        payload = request.get_json(silent=True) or {}
        coe = _parse_int(payload.get("coe"), "coe")
        pdf = str(payload.get("pdf", "N")).upper()
        if pdf not in {"S", "N"}:
            raise ArcaIntegrationError("'pdf' debe ser 'S' o 'N'.")
        result = _client().call_liquidacion_x_coe(coe, pdf)
        return jsonify(
            {
                "ok": True,
                "operation": "liquidacionXCoeConsultar",
                "request": {"coe": coe, "pdf": pdf},
                **result,
            }
        )
    except ArcaIntegrationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Error inesperado: {exc}"}), 500

